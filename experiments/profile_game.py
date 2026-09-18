import cProfile, pstats, io, contextlib, importlib.util
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m.agent
with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
    from kaggle_environments import make
A=load("main_v12.py","A"); B=load("main_v9.py","B")
def run():
    env=make("kaggriculture",configuration={"seed":30050000,"episodeSteps":720})
    env.run([A,B])
pr=cProfile.Profile(); pr.enable(); run(); pr.disable()
s=io.StringIO(); ps=pstats.Stats(pr,stream=s).sort_stats('cumulative')
ps.print_stats(25)
out=s.getvalue()
# print a trimmed view
for line in out.splitlines()[:40]:
    print(line)
