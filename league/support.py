"""Enhanced Game v2 shared runner/scoring (V13 lineage). No submission API calls."""
import argparse, concurrent.futures, contextlib, hashlib, importlib.util, io, json
import math, multiprocessing, os, random, shutil, sqlite3, statistics, time, zipfile
from pathlib import Path

BASE = dict(animals=16,hands=12,land=3,crop_bias=1.5,care_bias=1.3,fert_bias=1.,
            opponent_weight=0.,liquidate=False,drop_units=5,drop_value=1000000,
            cash_release=False,deposit_bias=.3,feed_fix=False,care_cap=1.3,
            plant_floor=12,hire_pace=2,workload_hiring=False,work_per_hand=8,
            keep_late_hands=True,land_util=.45,land_buffer=700,
            commitment=1.3,region_weight=.8,distance_weight=.65,dig_value=45,
            animal_deadline=16,land_deadline=18,expansion_hands=9,night_deposit=True)
BASE.update(liquidate=True,feed_fix=True,cash_release=True,plant_floor=40)
# Enhanced Game v2 phase keys. Defaults equal their base key, so an unsearched
# config reproduces v1 behavior; the league search moves the *_late variants.
BASE.update(late_day=24,crop_bias_late=BASE['crop_bias'],plant_floor_late=BASE['plant_floor'],deposit_bias_late=BASE['deposit_bias'])
BASE.update(strawberry_target=0)  # v14: 0 keeps v2 behavior; search establishes a large early strawberry crop
# v15: leader-profile mechanics (analysis/REPORT_deployment_diagnosis.md), all off by
# default so this reproduces v14 exactly. survival_bias>0 prices watering at a dying
# plant's replacement cost; fert_in_window opens fertilizer from the start of the
# yield window instead of one day before first yield; tiles_per_unit>0 caps planting
# at what the hands can water. Hand-picked combinations of these hurt on their own
# (see the report) -- they need the TPE search, not manual tuning.
BASE.update(survival_bias=0.,fert_in_window=0,tiles_per_unit=0,seed_stock=2)
# The 4th quadrant's own deadline (see policy_template.py). Defaults to
# land_deadline's own default (18), so an unset value reproduces the old
# single-deadline behavior exactly.
BASE.update(land4_deadline=18)
# Early-liquidity crop bias (see policy_template.py's crop_value). 0 reproduces v15
# exactly; the diagnosis's top-priority gap is day-10 cash, not yet touched by any
# existing parameter.
BASE.update(early_cash_bias=0.)
# v16 land-utilisation pair, from the 2026-09-23 replay study of a rank-2 leader
# (analysis/REPORT_leader_gap.md). plant_urgency=1 and seed_fill=0 reproduce v15.
# Together they target the one difference that dominates every other: the leader ends
# every day with zero bare owned tiles; we carry 20-40 while our hands idle.
BASE.update(plant_urgency=1., seed_fill=0)
# Time-to-cash discounting in crop_value (policy_template.py). cash_discount=1.0
# reproduces v15 exactly. This is the structural fix for the defect found on
# 2026-09-23: the scorer ranked crops by size alone and could not see that a melon
# ties a tile ~12 days for one payment while wheat recycles three times, which is the
# whole shape of the leader's early game.
# cash_patience frozen at 15000 rather than searched: every top trial in both search
# cycles picked 15000, the top of its range. Freezing it at the arbitrary old default
# instead would have quietly handicapped the runs that follow.
BASE.update(cash_discount=1., cash_patience=15000.)
# Expansion gate shape (policy_template.py). 0 = the averaged occupancy ratio this
# has always used; 1 = the emptiest owned quadrant, so "buy land only when what I
# already hold is full" becomes expressible at all. See analysis/REPORT_leader_gap.md.
BASE.update(land_fill_gate=0)
ENV_VERSION = "1.32.7"
CHECKPOINT_COPY = ''

def write_json(path, obj):
    path=Path(path);temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(obj,indent=2));temp.replace(path)
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load_agent(path, name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.agent
def render(template,params):
    return template.replace("CFG = {}  # replaced by the trainer","CFG = "+repr(dict(BASE,**params)),1)
def worker(job):
    candidate,opponent,seed,seat,*extras=job
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from kaggle_environments import make
    agent=load_agent(candidate,"candidate");rival=load_agent(opponent,"rival")
    elapsed=[];route_switches=0;observed_routes=0
    def timed(obs):
        nonlocal route_switches,observed_routes
        old=agent.__globals__.get('_MEMORY',{})
        previous=old.get('jobs',{}) if old.get('tick')==obs.day*24+obs.hour-1 and obs.hour else {}
        start=time.perf_counter();a=agent(obs);elapsed.append(time.perf_counter()-start)
        jobs=agent.__globals__.get('_MEMORY',{}).get('jobs',{})
        positions=[obs.farms[seat].farmer,*obs.farms[seat].hands]
        for i,job in previous.items():
            if i<len(positions) and tuple(positions[i])!=job[0]:
                observed_routes+=1;route_switches+=jobs.get(i)!=job
        return a
    env=make("kaggriculture",configuration={"seed":seed,"episodeSteps":720})
    env.run([timed,rival] if seat==0 else [rival,timed])
    final=env.steps[-1]
    if len(env.steps)!=720 or any(x.status!="DONE" or x.reward is None for x in final):
        raise RuntimeError("Agent error or incomplete game")
    if extras and extras[0] and final[seat].reward<final[1-seat].reward:
        import gzip
        with gzip.open(extras[0],'wt') as f:json.dump(env.toJSON(),f)
    first80=next((i for i,s in enumerate(env.steps) if s[seat].observation.farms[seat].money>=80000),None)
    land4=next((i for i,s in enumerate(env.steps) if len(s[seat].observation.farms[seat].unlocked_quadrants)==4),None)
    snapshots={}
    action_counts={}
    for s in env.steps[1:]:
        a=s[seat].action or {}
        for u in [a.get('farmer',[]),*a.get('hands',[])]:
            if u:action_counts[u[0]]=action_counts.get(u[0],0)+1
    for day in [5,10,15,20,25,28,29]:
        ob=env.steps[min(day*24+23,719)][seat].observation
        f=ob.farms[seat];tiles=[t for row in f.tiles for t in row]
        crops=sum(isinstance(t,dict) and bool(t.get('crop')) for t in tiles)
        animals=sum(isinstance(t,dict) and bool(t.get('animal')) for t in tiles)
        active_regions=set((x//5,y//5) for y,row in enumerate(f.tiles) for x,t in enumerate(row)
                           if isinstance(t,dict) and (t.get('crop') or t.get('animal')))
        # bare = owned but empty. The 2026-09-23 replay study made this the metric of
        # record: a rank-2 leader holds 0 bare tiles every day, we carry 20-40.
        bare=sum(t is None for t in tiles)
        # weeds = tiles already lost to two consecutive dry days. This is the direct
        # evidence of planting beyond watering throughput, which a productive-tile
        # count alone cannot show.
        weeds=sum(isinstance(t,dict) and t.get('kind')=='WEED' for t in tiles)
        snapshots[str(day)]=dict(cash=f.money,crops=crops,animals=animals,bare=bare,weeds=weeds,hands=len(f.hands),
                                quadrants=len(f.unlocked_quadrants),productive_quadrants=len(active_regions),
                                unwatered=sum(isinstance(t,dict) and bool(t.get('crop')) and not t.get('watered_today') for t in tiles),
                                unfed=sum(isinstance(t,dict) and bool(t.get('animal')) and not t.get('fed_today') for t in tiles),
                                carried_units=sum(sum(v.values()) for v in ob.private.inventories),
                                market_prices=dict(ob.market.prices),town=dict(ob.town),
                                by_quadrant={str((qx,qy)):sum(isinstance(t,dict) and bool(t.get('crop') or t.get('animal'))
                                    for y,row in enumerate(f.tiles) for x,t in enumerate(row) if (x//5,y//5)==(qx,qy))
                                    for qx,qy in [(0,0),(1,0),(0,1),(1,1)]})
    return dict(seed=seed,seat=seat,opponent=Path(opponent).name,cash=final[seat].reward,
                rival_cash=final[1-seat].reward,first80=first80,land4=land4,
                cash_before_last_two_days=env.steps[672][seat].observation.farms[seat].money,
                max_decision_seconds=max(elapsed),normal=True,snapshots=snapshots,actions=action_counts,
                route_switches=route_switches,route_continuation_opportunities=observed_routes)

def score(rows):
    # Winning dominates; time to $80k is a small secondary preference.
    terms=[]
    for r in rows:
        win=1. if r["cash"]>r["rival_cash"] else (.5 if r["cash"]==r["rival_cash"] else 0.)
        margin=max(-1.,min(1.,(r["cash"]-r["rival_cash"])/max(3000.,r["rival_cash"])))
        early=0. if r["first80"] is None else (719-r["first80"])/719
        # No income ceiling, no reward merely for buying assets. Early cash gets
        # little weight: excessive early saving can starve future production.
        terms.append(.65*win+.35*margin+.20*math.log1p(max(0,r['cash'])/80000)+.02*early)
    return statistics.mean(terms)

def summary(rows):
    hits=[r["first80"] for r in rows if r["first80"] is not None]
    return dict(games=len(rows),mean_cash=statistics.mean(r["cash"] for r in rows),
                minimum_cash=min(r["cash"] for r in rows),maximum_cash=max(r["cash"] for r in rows),
                mean_margin=statistics.mean(r["cash"]-r["rival_cash"] for r in rows),
                win_rate=statistics.mean(r["cash"]>r["rival_cash"] for r in rows),
                ties=sum(r["cash"]==r["rival_cash"] for r in rows),
                reach_80k_rate=len(hits)/len(rows),
                median_first_80k_turn_among_hits=statistics.median(hits) if hits else None,
                earliest_80k_turn=min(hits) if hits else None,
                four_quadrants_rate=statistics.mean(r["land4"] is not None for r in rows),
                mean_last_two_days_cash_gain=statistics.mean(r["cash"]-r["cash_before_last_two_days"] for r in rows),
                max_decision_seconds=max(r["max_decision_seconds"] for r in rows))

def seed_margin_interval(rows):
    by={}
    for r in rows:by.setdefault(r["seed"],[]).append(r["cash"]-r["rival_cash"])
    means=[statistics.mean(v) for v in by.values()]
    rng=random.Random(130)
    boot=sorted(statistics.mean(rng.choices(means,k=len(means))) for _ in range(2000))
    return [boot[50],boot[1949]]

def sample(trial):
    p=dict(BASE)
    p.update(
        animals=trial.suggest_int("animals",12,20,step=2),
        hands=trial.suggest_int("hands",10,12),
        land=trial.suggest_int("land",3,4),
        crop_bias=trial.suggest_float("crop_bias",.6,2.5),
        care_bias=trial.suggest_float("care_bias",.6,2.),
        fert_bias=trial.suggest_float("fert_bias",.6,1.8),
        opponent_weight=trial.suggest_categorical("opponent_weight",[0.,.5,1.]),
        liquidate=True,
        drop_units=trial.suggest_int("drop_units",2,6),
        drop_value=trial.suggest_categorical("drop_value",[250,500,1000,1000000]),
        cash_release=trial.suggest_categorical("cash_release",[False,True]),
        deposit_bias=trial.suggest_float("deposit_bias",.15,.65),
        feed_fix=True,
        care_cap=trial.suggest_categorical("care_cap",[1.3,2.,3.]),
        plant_floor=trial.suggest_categorical("plant_floor",[12,25,40,60,80]),
        hire_pace=trial.suggest_int("hire_pace",1,3),
        workload_hiring=trial.suggest_categorical("workload_hiring",[False,True]),
        work_per_hand=trial.suggest_categorical("work_per_hand",[6,8,10,12]),
        keep_late_hands=True,
        land_util=trial.suggest_categorical("land_util",[.35,.45,.55,.75]),
        land_buffer=trial.suggest_categorical("land_buffer",[300,700,1500]),
        commitment=trial.suggest_categorical('commitment',[1.,1.3,1.7]),
        region_weight=trial.suggest_categorical('region_weight',[.65,.8,1.]),
        distance_weight=trial.suggest_categorical('distance_weight',[.45,.65,.85]),
        dig_value=trial.suggest_categorical('dig_value',[20,45,75]),
        animal_deadline=trial.suggest_categorical('animal_deadline',[12,16,19]),
        expansion_hands=trial.suggest_categorical('expansion_hands',[7,9,11]),
        night_deposit=trial.suggest_categorical('night_deposit',[False,True]))
    return p

class Runner:
    def __init__(self,root,cfg,pool):
        self.root=root;self.cfg=cfg;self.pool=pool;self.cache={}
        self.started=time.monotonic();self.deadline=self.started+cfg["time_budget_minutes"]*60
        self.cache_path=root/"games.jsonl"
        if self.cache_path.exists():
            for line in self.cache_path.read_text().splitlines():
                try:
                    x=json.loads(line);self.cache[x["key"]]=x["result"]
                except json.JSONDecodeError: pass # interrupted final append
    def key(self,candidate,opponent,seed,seat):
        return ":".join([digest(candidate),digest(opponent),str(seed),str(seat),ENV_VERSION])
    def evaluate(self,candidate,opponents,seeds):
        rows=[];batch=[];keys=[]
        for seed in seeds:
            for opponent in opponents:
                for seat in [0,1]:
                    k=self.key(candidate,opponent,seed,seat)
                    if k in self.cache:
                        row=dict(self.cache[k]);row["opponent"]=opponent.name;rows.append(row)
                    else:
                        replay=None
                        if 19000000<=seed<19600000 and (seed-19000000)%10000<2:
                            replay=str(self.root/'replays'/f'{candidate.stem}_{opponent.stem}_{seed}_{seat}.json.gz')
                        keys.append(k);batch.append((str(candidate),str(opponent),seed,seat,replay))
        chunk=max(2,self.cfg["workers"]*2)
        for i in range(0,len(batch),chunk):
            if time.monotonic()>=self.deadline:raise TimeoutError("Run time budget reached")
            results=list(self.pool.map(worker,batch[i:i+chunk]))
            with self.cache_path.open("a") as f:
                for k,r in zip(keys[i:i+chunk],results):
                    self.cache[k]=r;rows.append(r)
                    f.write(json.dumps({"key":k,"result":r})+"\n")
                f.flush();os.fsync(f.fileno())
            if len(batch)>16:print("  evaluated",min(i+chunk,len(batch)),"/",len(batch),"games",flush=True)
        return rows

def checkpoint(root):
    # SQLite backup avoids copying an inconsistent live database.
    db=root/"study.db"
    if db.exists():
        with sqlite3.connect(str(db)) as src, sqlite3.connect(str(root/"study-backup.db")) as dest:src.backup(dest)
    path=root/"checkpoint.zip";temp=root/"checkpoint.zip.tmp"
    with zipfile.ZipFile(temp,"w",zipfile.ZIP_DEFLATED) as archive:
        names=["state.json","manifest.json","champion.py","main.py","games.jsonl","decision.json"]
        for name in names:
            p=root/name
            if p.exists():archive.write(p,name)
        if (root/"study-backup.db").exists():archive.write(root/"study-backup.db","study.db")
        for folder in ["trials","reports","replays"]:
            for p in (root/folder).glob("*"):
                if p.is_file():archive.write(p,str(p.relative_to(root)))
    temp.replace(path)
    if CHECKPOINT_COPY:
        mirror=Path(CHECKPOINT_COPY).expanduser()
        mirror.parent.mkdir(parents=True,exist_ok=True)
        if mirror.resolve()!=path.resolve():
            try:
                pending=mirror.with_suffix(mirror.suffix+'.tmp')
                shutil.copyfile(path,pending);pending.replace(mirror)
            except OSError as e:
                print('Checkpoint mirror failed; local checkpoint is intact:',str(e),flush=True)

def verify_export(root,opponent,seed):
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        from kaggle_environments import make
    e=make("kaggriculture",configuration={"seed":seed,"episodeSteps":720})
    e.run([str(root/"main.py"),str(opponent)])
    if len(e.steps)!=720 or any(x.status!="DONE" or x.reward is None for x in e.steps[-1]):
        raise RuntimeError("Exported file failed its loading test")
    # Preserve an inspectable replay, not only an aggregate score.
    import gzip
    (root/'replays').mkdir(exist_ok=True)
    with gzip.open(root/'replays'/f'filecheck_{seed}.json.gz','wt') as f:
        json.dump(e.toJSON(),f)
    return {"cash":[s.reward for s in e.steps[-1]],"status":[s.status for s in e.steps[-1]]}

def main(config_path):
    # Imported here, not at module scope: BASE/render/worker/summary are the parts
    # everything else uses, and they need no search library. Keeping optuna out of
    # the module import lets experiments/smoke_agent.py run as a fast pre-flight in
    # CI before the heavy requirements are installed.
    import optuna
    global CHECKPOINT_COPY
    cfg=json.loads(Path(config_path).read_text());root=Path(cfg["output_dir"]).resolve()
    CHECKPOINT_COPY=cfg.get('checkpoint_copy','')
    root.mkdir(parents=True,exist_ok=True)
    source=Path(__file__).resolve().parent
    for name in ["trials","reports","opponents","replays"]:(root/name).mkdir(exist_ok=True)
    template=(source/"policy_template.py").read_text()
    for version in ["v9","v11","v12"]:shutil.copyfile(source/f"main_{version}.py",root/"opponents"/f"main_{version}.py")
    for name,params in {
        "crop_heavy":dict(BASE,animals=6,hands=12,land=4,crop_bias=2.,plant_floor=60,land_util=.35),
        "livestock_heavy":dict(BASE,animals=20,hands=12,care_bias=1.8,feed_fix=True),
        "regional_mixed":dict(BASE,land=4,region_weight=.65,commitment=1.7),
        "reactive_market":dict(BASE,opponent_weight=.5,care_cap=3.,region_weight=1.,commitment=1.)}.items():
        (root/"opponents"/(name+".py")).write_text(render(template,params))
    # Extra executable opponents can be attached as a private Kaggle input.
    extras=[]
    for p in cfg.get("extra_opponents",[]):
        path=Path(p);target=root/"opponents"/("extra_"+digest(path)[:12]+".py")
        shutil.copyfile(path,target);extras.append(target)
    opponents=sorted((root/'opponents').glob('*.py'))
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        import kaggle_environments
    if kaggle_environments.__version__!=ENV_VERSION:raise RuntimeError("Wrong simulator version")
    signature=dict(template_sha=digest(source/"policy_template.py"),
                   trainer_sha=digest(Path(__file__)),opponents={p.name:digest(p) for p in opponents},
                   environment=ENV_VERSION,train_seed_count=cfg["train_seed_count"],
                   holdout_seed_count=cfg['holdout_seed_count'],v9_gate=cfg.get('v9_win_rate',.80))
    manifest=root/"manifest.json"
    if manifest.exists() and json.loads(manifest.read_text())!=signature:
        raise ValueError("Checkpoint belongs to a different search definition; use a new output directory")
    write_json(manifest,signature)
    state_path=root/"state.json"
    if state_path.exists():state=json.loads(state_path.read_text())
    else:
        state={"next_cycle":0,"tested_hashes":[],"champion":"v9","champion_sha":digest(root/"opponents/main_v9.py")}
        shutil.copyfile(root/"opponents/main_v9.py",root/"champion.py")
        write_json(state_path,state)
    if digest(root/"champion.py")!=state["champion_sha"]:raise ValueError("Checkpoint champion hash mismatch")
    shutil.copyfile(root/"champion.py",root/"main.py")
    write_json(root/"decision.json",{"export":state["champion"],"promoted":False,"status":"search_in_progress",
                                    "sha256":digest(root/"main.py")})
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study=optuna.create_study(study_name="kaggriculture-v13",direction="maximize",
        storage="sqlite:///"+str(root/"study.db"),load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=20260916+state["next_cycle"]),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=12,n_warmup_steps=1))
    for t in study.get_trials(deepcopy=False):
        if t.state==optuna.trial.TrialState.RUNNING:
            study.tell(t.number,state=optuna.trial.TrialState.FAIL)
    if not study.trials:
        for p in [BASE,dict(BASE,commitment=1.,region_weight=1.),
                  dict(BASE,land=4,land_util=.35),
                  dict(BASE,drop_value=1000,night_deposit=False,workload_hiring=True)]:
            study.enqueue_trial(p)
    checkpoint(root)
    context=multiprocessing.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max_workers=cfg["workers"],mp_context=context) as pool:
        runner=Runner(root,cfg,pool)
        search_deadline=runner.started+cfg["time_budget_minutes"]*60*cfg["search_fraction"]
        def objective(trial):
            params=sample(trial);candidate=root/"trials"/f"v13_trial_{trial.number:05d}.py"
            candidate.write_text(render(template,params))
            rows=[]
            for index in range(cfg["train_seed_count"]):
                if time.monotonic()>=search_deadline:raise optuna.TrialPruned("Search budget reached")
                rows+=runner.evaluate(candidate,opponents,[17000000+index])
                trial.report(score(rows),index)
                if trial.should_prune():raise optuna.TrialPruned()
            trial.set_user_attr("summary",summary(rows))
            trial.set_user_attr("sha256",digest(candidate))
            write_json(candidate.with_suffix(".json"),{"parameters":params,"summary":summary(rows),"games":rows})
            return score(rows)
        def completed(study,trial):
            checkpoint(root)
            value=round(trial.value,4) if trial.value is not None else None
            print("Trial",trial.number,trial.state.name,"score",value,
                  "elapsed_minutes",round((time.monotonic()-runner.started)/60,1),flush=True)
        remaining=max(0,cfg["total_trials"]-len(study.trials))
        # Queued warm starts already count as WAITING, but must still be executed.
        remaining+=sum(t.state==optuna.trial.TrialState.WAITING for t in study.trials)
        try:
            if not state.get('pending_holdout') and not cfg.get('evaluate_only',False):
                study.optimize(objective,n_trials=remaining,timeout=max(0,search_deadline-time.monotonic()),
                           callbacks=[completed],catch=(RuntimeError,))
        except TimeoutError:
            print("Search stopped at time budget; retaining safe export.",flush=True)
        complete=sorted((t for t in study.trials if t.state==optuna.trial.TrialState.COMPLETE),
                        key=lambda t:t.value,reverse=True)
        candidates=[];seen=set(state["tested_hashes"])
        for t in complete:
            path=root/"trials"/f"v13_trial_{t.number:05d}.py";sha=digest(path)
            if sha not in seen:
                candidates.append(path);seen.add(sha)
            if len(candidates)>=cfg["finalists"]:break
        if state.get('pending_holdout'):
            candidates=[root/'trials'/state['pending_holdout']['candidate']]
        decision={"export":state["champion"],"promoted":False,"status":"no_new_completed_candidate",
                  "sha256":digest(root/"main.py")}
        try:
            if candidates:
                validation=[]
                for candidate in ([] if state.get('pending_holdout') else candidates):
                    print("Validation:",candidate.name,flush=True)
                    rows=runner.evaluate(candidate,opponents,range(18000000,18000000+cfg["validation_seed_count"]))
                    record={"candidate":candidate.name,"score":score(rows),"summary":summary(rows),"games":rows}
                    write_json(root/"reports"/("validation_"+candidate.stem+".json"),record)
                    validation.append((record["score"],candidate))
                    checkpoint(root)
                if state.get('pending_holdout'):
                    winner=candidates[0];cycle=state['pending_holdout']['cycle']
                else:
                    _,winner=max(validation,key=lambda x:x[0])
                    cycle=state["next_cycle"];state["next_cycle"]+=1
                    state['pending_holdout']={'candidate':winner.name,'cycle':cycle}
                    state["tested_hashes"].append(digest(winner));write_json(state_path,state);checkpoint(root)
                holdout_opponents=list(opponents)
                if digest(root/"champion.py") not in [digest(p) for p in holdout_opponents]:
                    holdout_opponents=holdout_opponents+[root/"champion.py"]
                seeds=range(19000000+cycle*10000,19000000+cycle*10000+cfg["holdout_seed_count"])
                print("Fresh holdout:",winner.name,"cycle",cycle,flush=True)
                rows=runner.evaluate(winner,holdout_opponents,seeds)
                per={p.name:summary([r for r in rows if r["opponent"]==p.name]) for p in holdout_opponents}
                interval=seed_margin_interval(rows)
                per_intervals={p.name:seed_margin_interval([r for r in rows if r['opponent']==p.name]) for p in holdout_opponents}
                passed=(len(seeds)>=24 and interval[0]>0 and
                        per['main_v9.py']['win_rate']>=cfg.get('v9_win_rate',.80) and
                        per_intervals['main_v9.py'][0]>0 and
                        all(x["mean_margin"]>0 and x["win_rate"]>=.55 for x in per.values()) and
                        all(r['max_decision_seconds']<.8 for r in rows))
                report={"candidate":winner.name,"sha256":digest(winner),"summary":summary(rows),
                        "per_opponent":per,"per_opponent_margin_intervals":per_intervals,"seed_bootstrap_margin_interval":interval,"passed":passed,"games":rows,
                        "note":"Local baselines, not actual leaderboard leaders. Both seats share a seed cluster."}
                write_json(root/"reports"/f"holdout_cycle_{cycle:03d}.json",report)
                decision={"export":state["champion"],"promoted":False,"status":"holdout_failed",
                          "challenger":winner.name,"holdout":report["summary"],"sha256":digest(root/"main.py")}
                if passed:
                    shutil.copyfile(winner,root/"main.py")
                    try:report["file_loading_check"]=verify_export(root,root/"opponents/main_v9.py",9500000+cycle)
                    except Exception:
                        shutil.copyfile(root/"champion.py",root/"main.py");raise
                    shutil.copyfile(winner,root/"champion.py")
                    state.update(champion=winner.stem,champion_sha=digest(winner))
                    write_json(state_path,state)
                    decision.update(export=state["champion"],promoted=True,status="holdout_passed",
                                    sha256=digest(root/"main.py"))
                    write_json(root/"reports"/f"holdout_cycle_{cycle:03d}.json",report)
                state.pop('pending_holdout',None);write_json(state_path,state)
                write_json(root/'decision.json',decision);checkpoint(root)
                # Self-play is diagnostic, not a promotion criterion.
                if time.monotonic()<runner.deadline-60:
                    rows=runner.evaluate(root/"main.py",[root/"main.py"],range(19600000+cycle*100,19600000+cycle*100+cfg["selfplay_seed_count"]))
                    write_json(root/"reports"/f"selfplay_cycle_{cycle:03d}.json",{"summary":summary(rows),"games":rows})
        except TimeoutError:
            if not decision.get('promoted'):
                decision["status"]="time_budget_reached_keep_incumbent"
        except Exception as error:
            decision["status"]="evaluation_error_keep_incumbent"
            decision["error"]=type(error).__name__+": "+str(error)
            shutil.copyfile(root/"champion.py",root/"main.py")
        write_json(root/"decision.json",decision);checkpoint(root)
        print("FINAL:",json.dumps(decision,indent=2),flush=True)
    print("Upload file:",root/"main.py",flush=True)
    print("Resume archive:",root/"checkpoint.zip",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--config",required=True)
    args=parser.parse_args();main(args.config)
