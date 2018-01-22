"""Pseudo-builders for building and registering benchmarks.
"""
from SCons.Script import Action

def exists(env):
    return True

_benchmarks = []
def register_benchmark(env, test):
    _benchmarks.append(test.path)
    env.Alias('$BENCHMARK_ALIAS', test)

def benchmark_list_builder_action(env, target, source):
    ofile = open(str(target[0]), 'wb')
    try:
        for s in _benchmarks:
            print '\t' + str(s)
            ofile.write('%s\n' % s)
    finally:
        ofile.close()

def build_benchmark(env, target, source, **kwargs):
    libdeps = kwargs.get('LIBDEPS', [])
    libdeps.append('$BUILD_DIR/third_party/shim_benchmark')

    kwargs['LIBDEPS'] = libdeps

    result = env.Program(target, source, **kwargs)
    env.RegisterBenchmark(result[0])
    env.Install("#/build/benchmark/", result[0])
    return result

def generate(env):
    env.Command('$BENCHMARK_LIST', env.Value(_benchmarks),
            Action(benchmark_list_builder_action, "Generating $TARGET"))
    env.AddMethod(register_benchmark, 'RegisterBenchmark')
    env.AddMethod(build_benchmark, 'Benchmark')
    env.Alias('$BENCHMARK_ALIAS', '$BENCHMARK_LIST')
