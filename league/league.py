"""Enhanced Game v14: bounded, resumable league self-play; phase policy + occupancy/melon fixes.

TPE fits a model over explicit policy parameters. No external account access.
"""
import argparse
import concurrent.futures
import contextlib
import io
import json
import math
import multiprocessing
import os
from pathlib import Path
import random
import shutil
import sqlite3
import statistics
import time
import zipfile
import optuna
import support

BASE=dict(support.BASE)
SPACE={
    'animals':('int',6,22,2), 'hands':('int',8,12,1), 'land':('int',2,4,1),
    'crop_bias':('float',.6,2.5), 'care_bias':('float',.6,2.),
    'fert_bias':('float',.6,1.8), 'opponent_weight':('cat',0.,.5,1.),
    'drop_units':('int',2,6,1), 'drop_value':('cat',250,500,1000,1000000),
    'deposit_bias':('float',.15,.65), 'care_cap':('cat',1.3,2.,3.),
    'plant_floor':('cat',12,25,40,60,80), 'hire_pace':('int',1,3,1),
    'workload_hiring':('cat',False,True), 'work_per_hand':('cat',6,8,10,12),
    'land_util':('cat',0.,.35,.45,.55,.75), 'land_buffer':('cat',300,700,1500),
    'commitment':('cat',1.,1.3,1.7), 'region_weight':('cat',.65,.8,1.),
    'distance_weight':('cat',.45,.65,.85), 'dig_value':('cat',20,45,75),
    'animal_deadline':('cat',12,16,19), 'expansion_hands':('cat',7,9,11),
    'night_deposit':('cat',False,True),
    # Alternative strategies for exploiters, beyond a larger farm.
    'crop_style':('cat','balanced','quick','orchard'),
    'animal_style':('cat','balanced','milk','wool','eggs'),
    # Enhanced Game v2: late-game phase overrides (day>=late_day). Absent/default
    # values reproduce v1; the search explores whether a distinct late policy wins.
    'late_day':('cat',20,24,27),
    'crop_bias_late':('float',.6,2.5),
    'plant_floor_late':('cat',12,25,40,60,80),
    'deposit_bias_late':('float',.15,.65),
    # v14: how many strawberry plots to establish before applying the saturation discount.
    'strawberry_target':('int',0,40,4),
    # v15: leader-profile mechanics, see support.BASE. 0/off reproduces v14; the
    # hand-picked sweep in analysis/REPORT_deployment_diagnosis.md found each hurts
    # ALONE but they interact, so this is a TPE search problem, not a manual one.
    'survival_bias':('float',0.,2.5), 'fert_in_window':('cat',0,1),
    'tiles_per_unit':('cat',0,4,5,6,7,8), 'seed_stock':('cat',2,3,4,6),
    # Not previously searched (frozen at BASE's land_deadline=18); the diagnosis's
    # top-priority gap is establishing occupancy earlier, so this is now a knob.
    'land_deadline':('cat',10,12,15,18),
}

def sample(trial):
    p=dict(BASE)
    for k,s in SPACE.items():
        if s[0]=='int':p[k]=trial.suggest_int(k,s[1],s[2],step=s[3])
        elif s[0]=='float':p[k]=trial.suggest_float(k,s[1],s[2])
        else:p[k]=trial.suggest_categorical(k,list(s[1:]))
    return p

def warm_params(p):
    p=dict(BASE,**p)
    p.setdefault('crop_style','balanced');p.setdefault('animal_style','balanced')
    for k,s in SPACE.items():
        if s[0]=='cat' and p[k] not in s[1:]:p[k]=s[1]
        elif s[0] in ('int','float'):
            p[k]=max(s[1],min(s[2],p[k]))
            if s[0]=='int':p[k]=s[1]+round((p[k]-s[1])/s[3])*s[3]
    return {k:p[k] for k in SPACE}

def read_cfg(path):
    import ast
    for node in ast.parse(Path(path).read_text()).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CFG' for t in node.targets):
            return ast.literal_eval(node.value)
    return {}

def evaluate_gate(rows,cfg,champion_name):
    """No promotion from training or too few fresh seed clusters."""
    groups={name:[r for r in rows if r['opponent']==name] for name in sorted({r['opponent'] for r in rows})}
    per={n:support.summary(g) for n,g in groups.items()}
    intervals={n:support.seed_margin_interval(g) for n,g in groups.items()}
    required={'main_v9.py',champion_name}
    enough=bool(groups) and all(len({r['seed'] for r in g})>=24 for g in groups.values())
    normal=all(r['normal'] and r['max_decision_seconds']<cfg['max_decision_seconds'] for r in rows)
    baseline_ok=required.issubset(groups)
    if baseline_ok:
        baseline_ok=(per['main_v9.py']['win_rate']>=cfg['v9_win_rate'] and intervals['main_v9.py'][0]>0 and
                     per[champion_name]['win_rate']>=cfg['champion_win_rate'] and intervals[champion_name][0]>0)
    broad=all(p['mean_margin']>0 and p['win_rate']>=cfg['min_opponent_win_rate'] for p in per.values())
    pooled=support.seed_margin_interval(rows)
    promoted=bool(enough and normal and baseline_ok and broad and pooled[0]>0)
    # Counterstrategy: it demonstrably attacks the current champion, even when
    # its broader record is insufficient. It joins training, not the export.
    exploiter=bool(enough and normal and champion_name in per and
                  per[champion_name]['win_rate']>=cfg['champion_win_rate'] and intervals[champion_name][0]>0)
    return dict(promoted=promoted,exploiter=exploiter,per_opponent=per,
                margin_intervals=intervals,pooled_margin_interval=pooled,
                enough_fresh_seeds=enough,normal_and_fast=normal)

def target_met(rows,cfg):
    s=support.summary(rows)
    return (s['mean_cash']>=cfg['target_mean_cash'] and s['win_rate']>=cfg['target_win_rate']
            and s['reach_80k_rate']>=cfg['target_80k_rate'])

class League:
    def __init__(self,cfg,pool):
        self.cfg=cfg;self.root=Path(cfg['output_dir']).resolve();self.pool=pool
        self.source=Path(__file__).resolve().parent
        # Repo layout keeps fixed agents in ../agents/ alongside league.py's own
        # directory; the notebook's embedded-files flow writes everything flat next
        # to league.py in one directory. Support both without duplicating agents.
        self.agents_dir=(self.source.parent/'agents' if (self.source.parent/'agents'/'main_v9.py').exists()
                         else self.source)
        self.template_path=(self.source.parent/'policy'/'policy_template.py'
                            if (self.source.parent/'policy'/'policy_template.py').exists()
                            else self.source/'policy_template.py')
        self.root.mkdir(parents=True,exist_ok=True)
        for d in ['agents','candidates','reports','replays','sources']:(self.root/d).mkdir(exist_ok=True)
        self.started=time.monotonic();self.deadline=self.started+cfg['time_budget_minutes']*60
        self.template=self.template_path.read_text()
        fixed=[]
        # main_leader.py: a non-lineage opponent built to the strongest observed
        # leaderboard player's measured behavioural profile (analysis/
        # REPORT_deployment_diagnosis.md). Everything else here is our own lineage;
        # V14 passed the old pool 93.8-100% and then lost most games to this one.
        for name in ['main_v9.py','main_v11.py','main_v12.py','main_v14.py','main_leader.py']:
            shutil.copyfile(self.agents_dir/name,self.root/'agents'/name);fixed.append('agents/'+name)
        for name,p in {
            'stress_crops.py':dict(BASE,animals=6,hands=12,land=4,crop_bias=2.,plant_floor=60,land_util=.35,crop_style='orchard'),
            'stress_livestock.py':dict(BASE,animals=20,hands=12,care_bias=1.8,animal_style='milk')}.items():
            (self.root/'agents'/name).write_text(support.render(self.template,p));fixed.append('agents/'+name)
        for p in cfg.get('extra_opponents',[]):
            p=Path(p);name='external_'+support.digest(p)[:16]+'.py'
            shutil.copyfile(p,self.root/'agents'/name);fixed.append('agents/'+name)
        self.fixed=fixed
        contract={k:cfg[k] for k in ['train_seeds','selection_seeds','holdout_seeds','general_trials','exploiter_trials',
                  'finalists','history_size','selfplay_seeds','v9_win_rate','champion_win_rate','min_opponent_win_rate',
                  'max_decision_seconds','target_mean_cash','target_win_rate','target_80k_rate']}
        contract['sources']={n:support.digest(self.source/n) for n in ['league.py','support.py']}
        contract['sources']['policy_template.py']=support.digest(self.template_path)
        contract['fixed']={p:support.digest(self.root/p) for p in fixed}
        contract['environment']=support.ENV_VERSION
        manifest=self.root/'manifest.json'
        if manifest.exists() and json.loads(manifest.read_text())!=contract:
            raise ValueError('This checkpoint has different code, opponents or study settings. Start a new output folder.')
        support.write_json(manifest,contract)
        for n in ['league.py','support.py']:
            shutil.copyfile(self.source/n,self.root/'sources'/n)
        shutil.copyfile(self.template_path,self.root/'sources'/'policy_template.py')
        for n in ['main_v9.py','main_v11.py','main_v12.py','main_v14.py','main_leader.py']:
            shutil.copyfile(self.agents_dir/n,self.root/'sources'/n)
        if (self.root/'state.json').exists():self.state=json.loads((self.root/'state.json').read_text())
        else:
            # V14 is the strongest agent measured so far (beats V9 100%, V12 93.8% on
            # a 24-seed holdout); start the search from it, not the older V12.
            self.state=dict(cycle=0,phase='new_cycle',champion='agents/main_v14.py',
                            champion_sha=support.digest(self.root/'agents/main_v14.py'),
                            archives=[],tested_hashes=[],no_progress=0,promotions=0,
                            target_reached=False,restarts=0)
        for a in self.state['archives']:
            if support.digest(self.root/a['path'])!=a['sha256']:raise ValueError('Archived agent hash mismatch')
        if support.digest(self.root/self.state['champion'])!=self.state['champion_sha']:
            raise ValueError('Champion hash mismatch')
        self.state['restarts']+=1
        shutil.copyfile(self.root/self.state['champion'],self.root/'main.py')
        # Reuse the verified game runner; league transitions live only here.
        rcfg={'time_budget_minutes':cfg['time_budget_minutes'],'workers':cfg['workers']}
        self.runner=support.Runner(self.root,rcfg,pool);self.runner.deadline=self.deadline
        self.save('ready')

    def save(self,status):
        # A provisional file may have been copied for the loading test when an
        # interrupt arrived. Checkpoints must only export the accepted champion.
        accepted=self.root/self.state['champion']
        exported=self.root/'main.py'
        if not exported.exists() or support.digest(exported)!=self.state['champion_sha']:
            shutil.copyfile(accepted,exported)
        support.write_json(self.root/'state.json',self.state)
        decision=dict(status=status,export=self.state['champion'],sha256=self.state['champion_sha'],
                      promoted=self.state['promotions']>0,promotions=self.state['promotions'],
                      cycle=self.state['cycle'],phase=self.state['phase'],target_reached=self.state['target_reached'],
                      latest_report=self.state.get('latest_report'),
                      note='Local league results; no leaderboard rank guarantee. No Kaggle submission was made.')
        support.write_json(self.root/'decision.json',decision)
        db=self.root/'study.db'
        if db.exists():
            with sqlite3.connect(db) as src,sqlite3.connect(self.root/'study-backup.db') as dst:src.backup(dst)
        tmp=self.root/'checkpoint.zip.tmp'
        with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
            for name in ['state.json','manifest.json','main.py','games.jsonl','decision.json']:
                if (self.root/name).exists():z.write(self.root/name,name)
            if (self.root/'study-backup.db').exists():z.write(self.root/'study-backup.db','study.db')
            for folder in ['agents','candidates','reports','replays','sources']:
                for p in (self.root/folder).glob('*'):
                    if p.is_file():z.write(p,str(p.relative_to(self.root)))
        tmp.replace(self.root/'checkpoint.zip')
        mirror=self.cfg.get('checkpoint_copy','')
        if mirror:
            p=Path(mirror).expanduser()
            if p.resolve()!=(self.root/'checkpoint.zip').resolve():
                try:
                    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp')
                    shutil.copyfile(self.root/'checkpoint.zip',t);t.replace(p)
                except OSError as e:print('Local checkpoint saved; external copy failed:',str(e),flush=True)

    def paths(self,names):return [self.root/n for n in names]

    def seeds(self,phase,n):
        # Disjoint blocks across phases AND cycles. No recycled holdout seeds.
        return range(30000000+self.state['cycle']*100000+phase*10000,
                     30000000+self.state['cycle']*100000+phase*10000+n)

    def freeze_league(self):
        hist=self.state['archives'];limit=self.cfg['history_size']
        # Keep early history as well as recent counterstrategies. The full archive
        # is never deleted; this bounds the active evaluation cost.
        chosen=([hist[0]] if hist and limit else [])
        if limit>1:chosen+=hist[-(limit-1):]
        names=self.fixed+[self.state['champion']]+[a['path'] for a in chosen]
        seen=set();frozen=[]
        for n in names:
            sha=support.digest(self.root/n)
            if sha not in seen:frozen.append(n);seen.add(sha)
        self.state['league']=frozen
        self.state['frozen_champion']=next(n for n in frozen if support.digest(self.root/n)==self.state['champion_sha'])
        self.state['phase']='selfplay'
        self.save('cycle_started')
        print('CYCLE',self.state['cycle'],'champion',self.state['champion'],
              'opponents',len(frozen),'archives',len(hist),flush=True)

    def study(self,role):
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        return optuna.create_study(study_name=f"egv1_c{self.state['cycle']:03d}_{role}",
            direction='maximize',storage='sqlite:///'+str(self.root/'study.db'),load_if_exists=True,
            sampler=optuna.samplers.TPESampler(seed=731+self.state['cycle']*31+self.state['restarts'],n_startup_trials=4))

    def train(self,role):
        study=self.study(role);total=self.cfg[role+'_trials']
        opponents=([self.state['frozen_champion']] if role=='exploiter' else self.state['league'])
        phase=1 if role=='general' else 2
        if not study.trials:
            seeds=[warm_params(read_cfg(self.root/self.state['frozen_champion'])),warm_params(BASE)]
            if role=='exploiter':
                seeds[1]=warm_params(dict(BASE,land=4,animals=8,crop_style='quick',night_deposit=True))
            seeds+=self.state.get('warm_starts',[])[:2]
            for p in seeds[:total]:study.enqueue_trial(p)
        while True:
            if time.monotonic()>=self.deadline:raise TimeoutError()
            pending=self.state.get('pending_trial')
            finished=sum(t.state.is_finished() for t in study.trials)
            if not pending and finished>=total:break
            if not pending:
                trial=study.ask();params=sample(trial)
                name=f"egv1_c{self.state['cycle']:03d}_{role}_t{trial.number:04d}"
                path='candidates/'+name+'.py'
                (self.root/path).write_text(support.render(self.template,params))
                pending=dict(role=role,number=trial.number,params=params,path=path)
                self.state['pending_trial']=pending;self.save('trial_reserved')
            if pending['role']!=role:raise ValueError('Pending trial belongs to another phase')
            trial_no=pending['number'];candidate=self.root/pending['path']
            try:
                rows=self.runner.evaluate(candidate,self.paths(opponents),self.seeds(phase,self.cfg['train_seeds']))
                value=support.score(rows)
                done=next(t for t in study.trials if t.number==trial_no)
                if not done.state.is_finished():study.tell(trial_no,value)
                support.write_json(candidate.with_suffix('.json'),dict(parameters=pending['params'],summary=support.summary(rows),games=rows))
                print(role,'trial',trial_no,'score',round(value,4),'cash',round(support.summary(rows)['mean_cash']),flush=True)
            except RuntimeError as e:
                done=next(t for t in study.trials if t.number==trial_no)
                if not done.state.is_finished():study.tell(trial_no,state=optuna.trial.TrialState.FAIL)
                support.write_json(candidate.with_suffix('.json'),{'error':str(e),'parameters':pending['params']})
                print('Invalid trial',role,trial_no,str(e),flush=True)
            self.state.pop('pending_trial',None);self.save('training')
        self.state['phase']='exploiter' if role=='general' else 'select'
        self.save('training_phase_complete')

    def select(self):
        candidates=[];seen=set(self.state['tested_hashes']);seen.add(self.state['champion_sha'])
        warm=[]
        for role in ['general','exploiter']:
            good=sorted((t for t in self.study(role).trials if t.state==optuna.trial.TrialState.COMPLETE),key=lambda t:t.value,reverse=True)
            count=0
            for t in good:
                p=self.root/'candidates'/f"egv1_c{self.state['cycle']:03d}_{role}_t{t.number:04d}.py"
                if support.digest(p) in seen:continue
                seen.add(support.digest(p));candidates.append(p);count+=1
                warm.append(warm_params(read_cfg(p)))
                if count>=(self.cfg['finalists'] if role=='general' else 1):break
        self.state['warm_starts']=warm[:4]
        if not candidates:
            self.finish_cycle(False,'no_untested_candidate');return
        scores=[];attack_scores=[]
        for p in candidates:
            print('Selection',p.name,flush=True)
            rows=self.runner.evaluate(p,self.paths(self.state['league']),self.seeds(3,self.cfg['selection_seeds']))
            result=dict(candidate=p.name,score=support.score(rows),summary=support.summary(rows),games=rows)
            support.write_json(self.root/'reports'/('selection_'+p.stem+'.json'),result)
            scores.append((result['score'],str(p.relative_to(self.root))))
            if '_exploiter_' in p.name:
                direct=[r for r in rows if r['opponent']==Path(self.state['frozen_champion']).name]
                attack_scores.append((support.score(direct),str(p.relative_to(self.root))))
            self.save('selection')
        self.state['selected']=max(scores)[1]
        self.state.pop('selected_counter',None)
        if attack_scores:
            attacker=max(attack_scores)[1]
            if attacker!=self.state['selected']:
                self.state['selected_counter']=attacker
                self.state['tested_hashes'].append(support.digest(self.root/attacker))
        self.state['tested_hashes'].append(support.digest(self.root/self.state['selected']))
        self.state['phase']='holdout';self.save('holdout_reserved')

    def test(self,confirmation=False):
        candidate=self.root/self.state['selected'];phase=5 if confirmation else 4
        rows=self.runner.evaluate(candidate,self.paths(self.state['league']),self.seeds(phase,self.cfg['holdout_seeds']))
        gate=evaluate_gate(rows,self.cfg,Path(self.state['frozen_champion']).name)
        # Generate a loss replay from the first matching cached game. Replays are
        # optional diagnostics, never substituted for an adaptive opponent.
        if not confirmation and time.monotonic()<self.deadline-30:
            loss=next((r for r in rows if r['cash']<r['rival_cash']),None)
            if loss:
                opponent=next(p for p in self.paths(self.state['league']) if p.name==loss['opponent'])
                replay=self.root/'replays'/f"cycle_{self.state['cycle']:03d}_loss.json.gz"
                if not replay.exists():support.worker((str(candidate),str(opponent),loss['seed'],loss['seat'],str(replay)))
        name=f"reports/{'confirmation' if confirmation else 'holdout'}_c{self.state['cycle']:03d}.json"
        record=dict(candidate=self.state['selected'],sha256=support.digest(candidate),gate=gate,
                    summary=support.summary(rows),target_metrics_met=target_met(rows,self.cfg),games=rows)
        support.write_json(self.root/name,record);self.state['latest_report']=name
        self.state['pending_decision']=dict(report=name,confirmation=confirmation)
        self.state['phase']='commit';self.save('evaluation_complete')

    def archive(self,path,kind):
        sha=support.digest(path)
        for a in self.state['archives']:
            if a['sha256']==sha:return a['path']
        target=f"agents/egv1_{kind}_{sha[:16]}.py"
        shutil.copyfile(path,self.root/target)
        self.state['archives'].append(dict(path=target,sha256=sha,kind=kind,cycle=self.state['cycle']))
        return target

    def commit(self):
        pending=self.state['pending_decision'];report=json.loads((self.root/pending['report']).read_text())
        gate=report['gate'];candidate=self.root/self.state['selected']
        if pending['confirmation']:
            success=gate['promoted'] and report['target_metrics_met']
            self.state['target_reached']=bool(success)
            if success:self.finish_cycle(True,'target_confirmed')
            else:self.finish_or_counter(True,'target_confirmation_failed')
            return
        improved=gate['promoted'];added=False
        if improved:
            if time.monotonic()>=self.deadline:raise TimeoutError()
            shutil.copyfile(candidate,self.root/'main.py')
            try:
                report['file_loading_check']=support.verify_export(self.root,self.root/'agents/main_v9.py',
                    30000000+self.state['cycle']*100000+60000)
            except Exception:
                shutil.copyfile(self.root/self.state['champion'],self.root/'main.py');raise
            support.write_json(self.root/pending['report'],report)
            # Preserve the old champion to limit forgetting.
            self.archive(self.root/self.state['champion'],'history')
            path=self.archive(candidate,'champion')
            self.state.update(champion=path,champion_sha=support.digest(candidate),target_reached=False)
            self.state['promotions']+=1
            print('PROMOTED',path,flush=True)
        elif gate['exploiter']:
            known={a['sha256'] for a in self.state['archives']}
            added=support.digest(candidate) not in known
            if added:
                self.archive(candidate,'counter')
                print('New counterstrategy archived; champion retained.',flush=True)
        if improved and report['target_metrics_met']:
            self.state['phase']='confirm';self.save('target_requires_confirmation')
        else:self.finish_or_counter(improved or added,'champion_promoted' if improved else ('counter_added' if added else 'candidate_rejected'))

    def finish_or_counter(self,progress,status):
        if self.state.get('selected_counter'):
            self.state['cycle_progress']=progress;self.state['cycle_status']=status
            self.state['phase']='counter';self.save('counter_evaluation_reserved')
        else:self.finish_cycle(progress,status)

    def counter(self):
        candidate=self.root/self.state['selected_counter']
        opponent=self.root/self.state['frozen_champion']
        rows=self.runner.evaluate(candidate,[opponent],self.seeds(7,self.cfg['holdout_seeds']))
        gate=evaluate_gate(rows,self.cfg,opponent.name)
        name=f"reports/counter_c{self.state['cycle']:03d}.json"
        support.write_json(self.root/name,dict(candidate=str(candidate.relative_to(self.root)),
                           summary=support.summary(rows),gate=gate,games=rows))
        added=False
        if gate['exploiter']:
            added=support.digest(candidate) not in {a['sha256'] for a in self.state['archives']}
            self.archive(candidate,'counter')
        self.finish_cycle(added or self.state.get('cycle_progress',False),
                          'counter_added' if added else self.state.get('cycle_status','counter_rejected'))

    def finish_cycle(self,progress,status):
        self.state['no_progress']=0 if progress else self.state['no_progress']+1
        self.state['cycle']+=1;self.state['phase']='new_cycle'
        self.state.pop('pending_decision',None)
        self.save(status)
        print('Cycle finished:',status,'promotions',self.state['promotions'],flush=True)

    def run(self):
        while self.state['cycle']<self.cfg['max_cycles']:
            if self.state['target_reached'] and self.cfg['stop_on_target']:
                self.save('target_confirmed');return
            if self.state['no_progress']>=self.cfg['stagnation_cycles']:
                self.save('stagnation_limit');return
            if time.monotonic()>=self.deadline:raise TimeoutError()
            phase=self.state['phase']
            if phase=='new_cycle':self.freeze_league()
            elif phase=='selfplay':
                p=self.root/self.state['champion']
                rows=self.runner.evaluate(p,[p],self.seeds(0,self.cfg['selfplay_seeds']))
                support.write_json(self.root/'reports'/f"selfplay_c{self.state['cycle']:03d}.json",
                                   dict(summary=support.summary(rows),games=rows,note='Self-play does not establish relative strength.'))
                self.state['phase']='general';self.save('selfplay_complete')
            elif phase in ('general','exploiter'):self.train(phase)
            elif phase=='select':self.select()
            elif phase=='holdout':self.test()
            elif phase=='commit':self.commit()
            elif phase=='confirm':self.test(confirmation=True)
            elif phase=='counter':self.counter()
            else:raise ValueError('Unknown phase: '+str(phase))
        self.save('target_confirmed' if self.state['target_reached'] and self.cfg['stop_on_target'] else 'cycle_limit')

def main(config_path):
    cfg=json.loads(Path(config_path).read_text())
    for k in ['train_seeds','selection_seeds','holdout_seeds','selfplay_seeds']:
        if not 1<=cfg[k]<10000:raise ValueError('Seed counts must be 1..9999')
    if cfg['max_cycles']>=10000:raise ValueError('Use fewer than 10000 cycles')
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        import kaggle_environments
    if kaggle_environments.__version__!=support.ENV_VERSION:raise ValueError('Simulator version mismatch')
    with concurrent.futures.ProcessPoolExecutor(max_workers=cfg['workers'],mp_context=multiprocessing.get_context('spawn')) as pool:
        engine=League(cfg,pool)
        try:engine.run()
        except (TimeoutError,KeyboardInterrupt):
            engine.save('paused_resume_available')
            print('Paused. Resume the same checkpoint and settings.',flush=True)
        except Exception:
            shutil.copyfile(engine.root/engine.state['champion'],engine.root/'main.py')
            engine.save('error_resume_available');raise
        print('FINAL',json.dumps(json.loads((engine.root/'decision.json').read_text()),indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    main(parser.parse_args().config)
