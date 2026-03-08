#!/usr/bin/env python3
"""CLI entry point for the RA detection engine cascade.

Usage:
    python3 run.py --config configs/locked_baseline.yaml \\
                   --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv \\
                   --output results/

Runs the full cascade pipeline at the given config on the given data,
writing JSON results per primitive per timeframe to the output directory.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Run the RA cascade pipeline from CLI arguments."""
    parser = argparse.ArgumentParser(
        description="RA Detection Engine — run full cascade pipeline."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to YAML config file (e.g., configs/locked_baseline.yaml)",
    )
    parser.add_argument(
        "--data",
        required=True,
        help="Path to 1m CSV data file",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for JSON results",
    )
    parser.add_argument(
        "--timeframes",
        nargs="*",
        default=["1m", "5m", "15m"],
        help="Timeframes to run (default: 1m 5m 15m)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate paths
    config_path = Path(args.config)
    data_path = Path(args.data)
    output_dir = Path(args.output)

    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        return 1
    if not data_path.exists():
        logger.error("Data file not found: %s", data_path)
        return 1

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load config
    logger.info("Loading config: %s", config_path)
    from ra.config.loader import load_config
    config = load_config(config_path)

    # Load data
    logger.info("Loading data: %s", data_path)
    from ra.data.csv_loader import load_csv
    from ra.data.tf_aggregator import aggregate

    bars_1m = load_csv(data_path)
    logger.info("Loaded %d 1m bars", len(bars_1m))

    # Build timeframe bars
    bars_by_tf = {"1m": bars_1m}
    for tf in args.timeframes:
        if tf != "1m":
            bars_by_tf[tf] = aggregate(bars_1m, tf)
            logger.info("Aggregated to %s: %d bars", tf, len(bars_by_tf[tf]))

    # Build registry and cascade engine
    from ra.engine.cascade import (
        CascadeEngine,
        build_default_registry,
        extract_locked_params_for_cascade,
    )

    registry = build_default_registry()

    # Parse dependency graph from config
    dep_graph = {}
    for name, node in config.dependency_graph.items():
        dep_graph[name] = {"upstream": node.upstream}

    engine = CascadeEngine(registry, dep_graph)

    # Extract locked params
    params = extract_locked_params_for_cascade(config)

    # Run cascade
    logger.info("Running cascade on timeframes: %s", args.timeframes)
    results = engine.run(bars_by_tf, params, timeframes=args.timeframes)

    # Write results
    logger.info("Writing results to: %s", output_dir)
    summary = {}

    for primitive, tf_results in results.items():
        for tf_key, result in tf_results.items():
            # Serialize detections
            detections_out = []
            for det in result.detections:
                det_dict = {
                    "id": det.id,
                    "time": det.time.isoformat() if det.time else None,
                    "direction": det.direction,
                    "type": det.type,
                    "price": det.price,
                    "properties": det.properties,
                    "tags": det.tags,
                    "upstream_refs": det.upstream_refs,
                }
                detections_out.append(det_dict)

            output_data = {
                "primitive": result.primitive,
                "variant": result.variant,
                "timeframe": result.timeframe,
                "detection_count": len(result.detections),
                "detections": detections_out,
                "metadata": result.metadata,
                "params_used": result.params_used,
            }

            # Write to file
            filename = f"{primitive}_{tf_key}.json"
            out_path = output_dir / filename
            with open(out_path, "w") as f:
                json.dump(output_data, f, indent=2, default=str)

            det_count = len(result.detections)
            summary[f"{primitive}/{tf_key}"] = det_count
            if det_count > 0:
                logger.info(
                    "  %s/%s: %d detections -> %s",
                    primitive, tf_key, det_count, filename,
                )

    # Write summary
    summary_path = output_dir / "cascade_summary.json"
    with open(summary_path, "w") as f:
        json.dump(
            {
                "config": str(config_path),
                "data": str(data_path),
                "timeframes": args.timeframes,
                "timestamp": datetime.now().isoformat(),
                "detection_counts": summary,
                "total_detections": sum(summary.values()),
            },
            f,
            indent=2,
        )

    total = sum(summary.values())
    logger.info(
        "Cascade complete: %d primitives, %d total detections written to %s",
        len(results),
        total,
        output_dir,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
