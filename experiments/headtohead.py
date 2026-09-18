import time, contextlib, io, importlib.util, statistics
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m.agent
def play(a_path,b_path,seed):
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        from kaggle_environments import make
    A=load(a_path,'A'); B=load(b_path,'B')
    env=make("kaggriculture",configuration={"seed":seed,"episodeSteps":720})
    t0=time.perf_counter(); env.run([A,B]); dt=time.perf_counter()-t0
    f=env.steps[-1]
    return f[0].reward, f[1].reward, dt

def series(cand, opp, seeds, label):
    # play both seats: cand as A then cand as B, so seat advantage cancels
    margins=[]; cand_cash=[]; times=[]; wins=0; games=0
    for s in seeds:
        c0,o0,d0 = play(cand,opp,s)              # cand=seat0
        o1,c1,d1 = play(opp,cand,s)              # cand=seat1
        for cc,oc in [(c0,o0),(c1,o1)]:
            margins.append(cc-oc); cand_cash.append(cc); wins += cc>oc; games+=1
        times += [d0,d1]
    print(f"[{label}] games={games} win_rate={wins/games:.3f} "
          f"mean_cand_cash={statistics.mean(cand_cash):.0f} "
          f"mean_margin={statistics.mean(margins):+.0f} "
          f"min_margin={min(margins):+.0f} | {statistics.mean(times):.2f}s/game")
    return dict(games=games,win_rate=wins/games,mean_margin=statistics.mean(margins))

seeds=[30040000+i for i in range(6)]
series("main_v12.py","main_v9.py",seeds,"V12 vs V9")
series("main_v9.py","main_v9.py",seeds,"V9 vs V9 (sanity)")
