#!/usr/bin/env python3

import argparse
import asyncio
import os

import aiohttp
from tqdm.asyncio import tqdm_asyncio

MAX_CONCURRENT = 64
TIMEOUT = aiohttp.ClientTimeout(total=30)


async def download_tile(
        sem: asyncio.Semaphore,
        session: aiohttp.ClientSession,
        game_version: str,
        map_type: str,
        resolution: int,
        x: int,
        y: int,
):
    out_dir = f"static/images/map/tiles/{game_version}_{map_type}_{resolution}"
    os.makedirs(out_dir, exist_ok=True)

    async with sem:
        x_dir = os.path.join(out_dir, str(x))
        os.makedirs(x_dir, exist_ok=True)

        out_path = os.path.join(x_dir, f"{y}.webp")
        if os.path.exists(out_path):
            return

        url = (
            f"https://static.xam.nu/dayz/maps/"
            f"chernarusplus/{game_version}/{map_type}/{resolution}/{x}/{y}.webp"
        )

        async with session.get(url) as r:
            r.raise_for_status()

            if r.content_type != "image/webp":
                raise RuntimeError(
                    f"{x}/{y}: invalid content-type {r.content_type}"
                )

            data = await r.read()
            with open(out_path, "wb") as f:
                f.write(data)


async def download_all_tiles(
        game_version: str,
        map_type: str,
        resolution: int,
):
    grid_size = 2 ** resolution
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async with aiohttp.ClientSession(
            timeout=TIMEOUT,
    ) as session:
        tasks = [
            asyncio.create_task(
                download_tile(
                    sem, session,
                    game_version, map_type, resolution,
                    x, y
                ),
                name=f"download_tile_{game_version}_{map_type}_{resolution}_{x}_{y}",
            )
            for x in range(grid_size)
            for y in range(grid_size)
        ]

        try:
            await tqdm_asyncio.gather(
                *tasks,
                desc=f"{game_version}/{map_type}/{resolution}",
            )
        except:
            for t in tasks:
                t.cancel()
            raise


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download DayZ map tiles from xam.nu"
    )

    parser.add_argument(
        "--version",
        required=True,
        help="Game version (e.g. 1.27)",
    )

    parser.add_argument(
        "--map-type",
        required=True,
        choices=("satellite", "topographic"),
        help="Map type",
    )

    parser.add_argument(
        "--resolution",
        type=int,
        help="Single resolution (e.g. 8)",
    )

    parser.add_argument(
        "--resolution-range",
        nargs=2,
        type=int,
        metavar=("FROM", "TO"),
        help="Resolution range, e.g. 5 8",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if not args.resolution and not args.resolution_range:
        raise SystemExit(
            "❌ Нужно указать --resolution или --resolution-range"
        )

    resolutions: list[int]

    if args.resolution_range:
        start, end = args.resolution_range
        resolutions = list(range(start, end + 1))
    else:
        resolutions = [args.resolution]

    for res in resolutions:
        asyncio.run(
            download_all_tiles(
                game_version=args.version,
                map_type=args.map_type,
                resolution=res,
            )
        )


if __name__ == "__main__":
    main()
