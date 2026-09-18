import time, contextlib, io, importlib.util, sys
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m.agent
def play(a_path,b_path,seed):
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        from kaggle_environments import make
    A=load(a_path,'A'); B=load(b_path,'B')
    env=make("kaggriculture",configuration={"seed":seed,"episodeSteps":720})
    t0=time.perf_counter(); env.run([A,B]); dt=time.perf_counter()-t0
    final=env.steps[-1]
    ok = len(env.steps)==720 and all(x.status=="DONE" and x.reward is not None for x in final)
    return final[0].reward, final[1].reward, dt, ok, len(env.steps)

if __name__=="__main__":
    a,b=sys.argv[1],sys.argv[2]
    seeds=[int(s) for s in sys.argv[3].split(",")]
    tot=0
    for s in seeds:
        r0,r1,dt,ok,n=play(a,b,s); tot+=dt
        win = "A" if r0>r1 else ("B" if r1>r0 else "tie")
        print(f"seed {s:>10} | A={r0:>8.0f} B={r1:>8.0f} | win={win:3s} | {dt:5.2f}s | steps={n} ok={ok}")
    print(f"total {tot:.2f}s over {len(seeds)} games -> {tot/len(seeds):.2f}s/game")
