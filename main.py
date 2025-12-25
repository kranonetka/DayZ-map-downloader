#!/usr/bin/env python3

import argparse
import asyncio
import os
import shutil
from typing import Iterable

import aiohttp
from PIL import Image
from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio

MAX_CONCURRENT = 64
TIMEOUT = aiohttp.ClientTimeout(total=30)


async def download_tile(
        sem: asyncio.Semaphore,
        target_dir: str,
        session: aiohttp.ClientSession,
        game_version: str,
        map_type: str,
        resolution: int,
        x: int,
        y: int,
):
    out_dir = f"{target_dir}/{game_version}_{map_type}_{resolution}x{resolution}"
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


async def glue_tiles(tiles_dir: str, out_dir: str, game_version: str, map_type: str, resolution: int):
    os.makedirs(out_dir, exist_ok=True)

    grid_size = 2 ** resolution

    atlas_path = os.path.join(out_dir, f"{map_type}_{game_version}_{grid_size}x{grid_size}.webp")

    canvas_width = grid_size * 256
    canvas_height = grid_size * 256

    atlas = Image.new("RGBA", (canvas_width, canvas_height))

    total_tiles = grid_size * grid_size
    with tqdm(total=total_tiles, desc=f"Glue {game_version}/{map_type}/{resolution}", unit="tile") as pbar:
        for x in range(grid_size):
            for y in range(grid_size):
                tile_path = os.path.join(tiles_dir, str(x), f"{y}.webp")
                tile = Image.open(tile_path).convert("RGBA")
                atlas.paste(tile, (x * 256, y * 256), tile)
                pbar.update(1)

    atlas.save(atlas_path, format="WEBP")
    print(f"Saved map: {atlas_path}")


async def download_all_tiles(
        game_version: str,
        map_type: str,
        resolution: int,
        dir: str
):
    grid_size = 2 ** resolution
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async with aiohttp.ClientSession(
            timeout=TIMEOUT,
    ) as session:
        tasks = [
            asyncio.create_task(
                download_tile(
                    sem, dir, session,
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
                desc=f"Download {game_version}/{map_type}/{resolution}",
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

    parser.add_argument(
        "--tmp-dir",
        type=str,
        default="tmp",
        help="Tmp dir to download tiles from",
    )

    parser.add_argument(
        "--out-dir",
        type=str,
        default="maps",
        help="Dir to store downloaded glued tiles",
    )

    return parser.parse_args()


async def main():
    args = parse_args()

    if not args.resolution and not args.resolution_range:
        raise SystemExit(
            "❌ Нужно указать --resolution или --resolution-range"
        )

    resolutions: Iterable[int]

    if args.resolution_range:
        start, end = args.resolution_range
        resolutions = range(start, end + 1)
    else:
        resolutions = [args.resolution]

    for res in resolutions:
        await download_all_tiles(
            game_version=args.version,
            map_type=args.map_type,
            resolution=res,
            dir=args.tmp_dir
        )

        current_map_tiles_dir = os.path.join(
            args.tmp_dir,
            f'{args.version}_{args.map_type}_{res}x{res}'
        )

        await glue_tiles(current_map_tiles_dir, args.out_dir, args.version, args.map_type, res)

        shutil.rmtree(args.tmp_dir)


if __name__ == "__main__":
    asyncio.run(main())
