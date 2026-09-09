import subprocess as sp
from typing import List, Optional

from anipy_api.player.base import PlayCallback, SubProcessPlayerBase


class Iina(SubProcessPlayerBase):
    """The [iina](https://iina.io) subprocess player class.

    For detailed documentation about the functions and arguments have a look at the [base class][anipy_api.player.base.SubProcessPlayerBase].
    """

    def __init__(
        self,
        player_path: str,
        extra_args: List[str] = [],
        play_callback: Optional[PlayCallback] = None,
    ):
        self.extra_args = extra_args
        self.player_args_template = [
            "--no-stdin",
            "--mpv-force-media-title={media_title}",
            "--mpv-referrer={referrer}",
            "{stream_url}",
            *extra_args,
        ]

        super().__init__(
            player_path=player_path, extra_args=extra_args, play_callback=play_callback
        )

    def play_title(self, anime, stream):
        subs = self._get_media_sub(stream, anime)
        cmd = [
            self._player_exec,
            "--no-stdin",
            f"--mpv-force-media-title={self._get_media_title(anime, stream)}",
            "--mpv-slang=ara,ar,eng,en",
        ]
        if stream.referrer:
            cmd.append(f"--mpv-referrer={stream.referrer}")
        best_sub = ""
        ara_subs = []
        for k, v in subs.items():
            if k.lower().startswith("arabic"):
                ara_subs.append(v)
        import os as _os
        want = int(_os.environ.get("ANIPY_ARABIC_INDEX", "0"))
        if len(ara_subs) > want:
            best_sub = ara_subs[want]
        elif ara_subs:
            best_sub = ara_subs[0]
        if best_sub:
            cmd.append(f"--mpv-sub-files={best_sub}")
        cmd.extend(self.extra_args)
        cmd.append(stream.url)
        if isinstance(self._sub_proc, sp.Popen):
            self.kill_player()
        self._sub_proc = self._open_sproc(cmd)
        self._call_play_callback(anime, stream)
