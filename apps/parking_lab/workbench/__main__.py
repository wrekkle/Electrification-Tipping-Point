import argparse
import json
from pathlib import Path
from .config import Config
from .experiments import compare, export_run, write_output
from .server import serve
from .simulation import Simulation


def main():
    ap = argparse.ArgumentParser(description="停车场仿真与在线学习实验台（合成实验 + 公开数据事件契约）")
    ap.add_argument("command", choices=["serve", "run", "compare", "traffic"],
                    nargs="?", default="serve")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--config", help="UTF-8 JSON配置路径")
    ap.add_argument("--seeds", help="对比用逗号分隔种子，如42,43,44")
    ap.add_argument("--out", help="显式指定一个尚不存在的输出目录")
    ap.add_argument("--params", help="车流生成参数文件（traffic 子命令，须为 round8 公开数据标定参数）")
    ap.add_argument("--seed", help="车流随机种子（traffic 子命令，默认 42）")
    ap.add_argument("--split", help="车流参数集：train（默认，训练场站估计）或 cohort（参考全体）")
    args = ap.parse_args()
    if args.command == "traffic":
        from . import traffic_gen
        if not args.params:
            ap.error("traffic 子命令必须用 --params 指向 fitted_parameters.json")
        params = traffic_gen.load_params(args.params)
        seed = int(args.seed) if args.seed else 42
        split = args.split or "train"
        arrivals, meta = traffic_gen.generate(params, seed, split=split)
        if args.out:
            traffic_gen.save_traffic(args.out, arrivals, meta)
            print(json.dumps({"out": str(Path(args.out).resolve()), "n_arrivals": len(arrivals),
                              "stream_hash": meta["stream_hash"], "params_hash": meta["params_hash"],
                              "split": meta["split"]}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"meta": meta, "n_arrivals": len(arrivals)},
                             ensure_ascii=False, indent=2, allow_nan=False))
        return
    if args.command == "serve":
        if not 0 <= args.port <= 65535:
            ap.error("端口必须为0至65535")
        serve(args.port)
        return
    raw = json.loads(Path(args.config).read_text(encoding="utf-8-sig")) if args.config else {}
    c = Config.parse(raw)
    if args.command == "compare":
        seeds = [int(x) for x in args.seeds.split(",")] if args.seeds else None
        result = compare(c, seeds)
    else:
        sim = Simulation(c)
        sim.run()
        result = export_run(sim)
    if args.out:
        print(write_output(args.out, result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
