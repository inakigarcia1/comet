import unittest

from comet.services.compatibility.filename_parser import parse_filename


def _check(filename: str, **expected):
    parsed = parse_filename(filename)
    for key, value in expected.items():
        if key == "resolution":
            assert parsed.resolution.value == value[0], (filename, parsed.resolution, value)
            assert parsed.resolution.source == value[1], (filename, parsed.resolution, value)
        elif key == "codec":
            assert parsed.codec.value == value[0], (filename, parsed.codec, value)
            assert parsed.codec.source == value[1], (filename, parsed.codec, value)
        elif key == "profile":
            assert parsed.profile.value == value[0], (filename, parsed.profile, value)
            assert parsed.profile.source == value[1], (filename, parsed.profile, value)
        elif key == "bit":
            assert parsed.bit_depth.value == value[0], (filename, parsed.bit_depth, value)
            if value[1] == "explicit-or-inferred":
                assert parsed.bit_depth.source in ("explicit", "inferred", "inferred_high")
            else:
                assert parsed.bit_depth.source == value[1], (filename, parsed.bit_depth, value)
        elif key == "hdr":
            assert parsed.hdr.value == value[0], (filename, parsed.hdr, value)
            assert parsed.hdr.source == value[1], (filename, parsed.hdr, value)
        elif key == "dv":
            assert parsed.dolby_vision.value is True
            assert parsed.dolby_vision.source == "explicit"
        elif key == "dv_unknown":
            assert parsed.dolby_vision.source == "unknown"
        elif key == "fps":
            assert parsed.fps.value == value, (filename, parsed.fps, value)
            assert parsed.fps.source == "explicit"
        elif key == "fps_unknown":
            assert parsed.fps.source == "unknown", (filename, parsed.fps)
        elif key == "audio":
            assert parsed.audio_codec.value == value, (filename, parsed.audio_codec, value)
            assert parsed.audio_codec.source == "explicit"
        elif key == "channels":
            assert parsed.audio_channels.value == value, (filename, parsed.audio_channels, value)
            assert parsed.audio_channels.source == "explicit"
        elif key == "atmos":
            assert parsed.atmos.value is True and parsed.atmos.source == "explicit"
        elif key == "width":
            assert parsed.width == value, (filename, parsed.width, value)
        elif key == "height":
            assert parsed.height == value, (filename, parsed.height, value)
        elif key == "interlaced":
            assert parsed.interlaced is True
        elif key == "conflicts":
            assert bool(parsed.conflicts) is value, (filename, parsed.conflicts)
        elif key == "level":
            assert parsed.level.value == value, (filename, parsed.level, value)
            assert parsed.level.source == "explicit"
        else:
            raise AssertionError(key)


E = "explicit"
IH = "inferred_high"
I = "inferred"
U = "unknown"


class FilenameMediaParserTests(unittest.TestCase):
    def test_release_names(self):
        cases = [
            (
                "UNABOMBER.2026.2160p.NF.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-FHC.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True, fps_unknown=True),
            ),
            (
                "Dune.Part.Two.2024.2160p.WEB-DL.x265.10bit.HDR10.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(10, E), profile=("Main10", IH), hdr=("hdr10", E), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Oppenheimer.2023.2160p.UHD.BluRay.REMUX.HEVC.DV.HDR.TrueHD.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr", E), bit=(10, IH), profile=("Main10", IH), audio="truehd", atmos=True),
            ),
            (
                "The.Batman.2022.1080p.BluRay.x264.DTS.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), bit=(None, U), audio="dts", fps_unknown=True),
            ),
            (
                "Blade.Runner.2049.2017.2160p.UHD.BluRay.x265.10bit.HDR10.DTS-HD.MA.7.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(10, E), profile=("Main10", IH), hdr=("hdr10", E), audio="dtshd", channels="7.1"),
            ),
            (
                "The.Last.of.Us.S01E01.2160p.MAX.WEB-DL.DDP5.1.Atmos.DV.HDR.H265.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Stranger.Things.S04E09.2160p.NF.WEB-DL.DDP5.1.DV.H265.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=(None, U), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1"),
            ),
            (
                "Breaking.Bad.S05E16.1080p.BluRay.x264.DTS.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="dts", bit=(None, U)),
            ),
            (
                "Severance.S02E01.2160p.ATVP.WEB-DL.DDP5.1.Atmos.DV.HDR.HEVC.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "3.Body.Problem.S01E01.2160p.NF.WEB-DL.DDP5.1.Atmos.H265.HDR.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True, dv_unknown=True),
            ),
            (
                "Dark.S03E08.2160p.NF.WEB-DL.H265.10bit.HDR10.DDP5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(10, E), profile=("Main10", IH), hdr=("hdr10", E), audio="eac3", channels="5.1"),
            ),
            (
                "1899.S01E01.1080p.NF.WEB-DL.x264.DDP5.1.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="eac3", channels="5.1", bit=(None, U), fps_unknown=True),
            ),
            (
                "1923.S02E01.2160p.WEB-DL.H265.HDR10.DDP5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1"),
            ),
            (
                "24.S01E01.720p.WEB-DL.x264.AAC2.0.mkv",
                dict(resolution=("720p", E), codec=("avc", E), audio="aac", channels="2.0", fps_unknown=True, bit=(None, U)),
            ),
            (
                "The.100.S01E01.1080p.WEB-DL.H264.AAC2.0.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="aac", channels="2.0", bit=(None, U)),
            ),
            (
                "1917.2019.2160p.UHD.BluRay.x265.10bit.HDR10.DTS-HD.MA.7.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(10, E), profile=("Main10", IH), hdr=("hdr10", E), audio="dtshd", channels="7.1"),
            ),
            (
                "2001.A.Space.Odyssey.1968.2160p.UHD.BluRay.HEVC.HDR10.TrueHD7.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="truehd", channels="7.1"),
            ),
            (
                "8.Bit.Christmas.2021.1080p.WEB-DL.H264.DDP5.1.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="eac3", channels="5.1", bit=(None, U), fps_unknown=True),
            ),
            (
                "10.Things.I.Hate.About.You.1999.1080p.BluRay.x264.DTS.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="dts", bit=(None, U)),
            ),
            (
                "Se7en.1995.2160p.UHD.BluRay.x265.10bit.HDR10.TrueHD.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(10, E), hdr=("hdr10", E), profile=("Main10", IH), audio="truehd", atmos=True),
            ),
            (
                "Catch-22.S01E01.1080p.WEB-DL.H264.AAC2.0.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="aac", channels="2.0", fps_unknown=True),
            ),
            (
                "District.9.2009.2160p.UHD.BluRay.x265.10bit.HDR.DTS-HD.MA.5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(10, E), hdr=("hdr", E), profile=("Main10", IH), audio="dtshd", channels="5.1"),
            ),
            (
                "Apollo.13.1995.2160p.UHD.BluRay.HEVC.HDR10.DTS-X.7.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="dtsx", channels="7.1"),
            ),
            (
                "12.Angry.Men.1957.1080p.BluRay.x264.FLAC.1.0.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="flac", channels="1.0", fps_unknown=True),
            ),
            (
                "9-1-1.S08E01.1080p.WEB-DL.x264.AAC.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="aac", bit=(None, U), fps_unknown=True),
            ),
            (
                "Formula.1.Drive.to.Survive.S07E01.2160p.NF.WEB-DL.H265.DV.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, bit=(10, IH), profile=("Main10", IH), hdr=(None, U), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Love.Death.and.Robots.S04E01.2160p.NF.WEB-DL.HEVC.HDR10.DDP5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1"),
            ),
            (
                "Arcane.S02E09.1080p.NF.WEB-DL.AV1.Opus.mkv",
                dict(resolution=("1080p", E), codec=("av1", E), audio="opus", bit=(None, U), profile=(None, U)),
            ),
            (
                "Big.Buck.Bunny.2160p.AV1.10bit.HDR10.Opus.webm",
                dict(resolution=("2160p", E), codec=("av1", E), bit=(10, E), hdr=("hdr10", E), audio="opus", profile=(None, U)),
            ),
            (
                "sample_3840x2160_60fps_hevc_main10_hdr10.mkv",
                dict(width=3840, height=2160, resolution=("2160p", E), fps=60, codec=("hevc", E), profile=("Main10", E), bit=(10, I), hdr=("hdr10", E)),
            ),
            (
                "3840x2160_HEVC_24fps.mkv",
                dict(width=3840, height=2160, resolution=("2160p", E), codec=("hevc", E), fps=24, profile=(None, U), bit=(None, U)),
            ),
            (
                "2160p.mkv",
                dict(resolution=("2160p", E), codec=(None, U), bit=(None, U), hdr=(None, U), profile=(None, U)),
            ),
            (
                "video.mkv",
                dict(resolution=(None, U), codec=(None, U), bit=(None, U)),
            ),
            (
                "stream_01.mp4",
                dict(resolution=(None, U), codec=(None, U), fps_unknown=True, bit=(None, U)),
            ),
            (
                "4K.H265.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(None, U), profile=(None, U)),
            ),
            (
                "UHD_HDR_HEVC.mkv",
                dict(resolution=("2160p", E), hdr=("hdr", E), codec=("hevc", E), bit=(10, IH), profile=("Main10", IH)),
            ),
            (
                "1080p.H264.mp4",
                dict(resolution=("1080p", E), codec=("avc", E)),
            ),
            (
                "720p.x265.10bit.mkv",
                dict(resolution=("720p", E), codec=("hevc", E), bit=(10, E), profile=("Main10", IH)),
            ),
            (
                "2160p.AV1.10bit.HDR10+.mkv",
                dict(resolution=("2160p", E), codec=("av1", E), bit=(10, E), hdr=("hdr10+", E), profile=(None, U)),
            ),
            (
                "2160p.VP9.Profile2.HDR10.webm",
                dict(resolution=("2160p", E), codec=("vp9", E), profile=("Profile2", E), hdr=("hdr10", E), bit=(10, IH)),
            ),
            (
                "2160p.VP9.HDR.webm",
                dict(resolution=("2160p", E), codec=("vp9", E), hdr=("hdr", E), bit=(10, I), profile=(None, U)),
            ),
            (
                "1080p.VP8.Vorbis.webm",
                dict(resolution=("1080p", E), codec=("vp8", E), audio="vorbis"),
            ),
            (
                "1080i.MPEG2.AC3.ts",
                dict(resolution=("1080i", E), interlaced=True, codec=("mpeg2", E), audio="ac3"),
            ),
            (
                "576p.XviD.MP3.avi",
                dict(resolution=("576p", E), codec=("xvid", E), audio="mp3"),
            ),
            (
                "480p.H264.AAC.mp4",
                dict(resolution=("480p", E), codec=("avc", E), audio="aac"),
            ),
            (
                "2160p.H265.8bit.SDR.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(8, E), hdr=("sdr", E), profile=("Main", IH)),
            ),
            (
                "2160p.HEVC.Main.8bit.SDR.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), profile=("Main", E), bit=(8, E), hdr=("sdr", E), conflicts=False),
            ),
            (
                "2160p.HEVC.Main10.10bit.HDR10.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), profile=("Main10", E), bit=(10, E), hdr=("hdr10", E)),
            ),
            (
                "2160p.HEVC.Main10.L5.0.23.976fps.HDR10.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), profile=("Main10", E), bit=(10, I), level="5.0", fps=23.976, hdr=("hdr10", E)),
            ),
            (
                "2160p.HEVC.Main10.Level5.1.60fps.HDR10.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), profile=("Main10", E), bit=(10, I), level="5.1", fps=60, hdr=("hdr10", E)),
            ),
            (
                "1080p.x264.Hi10P.FLAC.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), profile=("High10", E), bit=(10, "explicit-or-inferred"), audio="flac"),
            ),
            (
                "One.Piece.S01E01.1080p.BluRay.H264.Hi10P.FLAC.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), profile=("High10", E), bit=(10, "explicit-or-inferred"), audio="flac"),
            ),
            (
                "Frieren.Beyond.Journeys.End.S01E01.1080p.HEVC.10bit.Opus.mkv",
                dict(resolution=("1080p", E), codec=("hevc", E), bit=(10, E), profile=("Main10", IH), audio="opus"),
            ),
            (
                "Planet.Earth.III.S01E01.2160p.UHD.BluRay.HEVC.HLG.TrueHD7.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hlg", E), bit=(10, IH), profile=("Main10", IH), audio="truehd", channels="7.1"),
            ),
            (
                "Top.Gun.Maverick.2022.2160p.WEB-DL.H265.DV.HDR10.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Mad.Max.Fury.Road.2015.2160p.UHD.BluRay.HEVC.DV.HDR10+.TrueHD.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr10+", E), bit=(10, IH), profile=("Main10", IH), audio="truehd", atmos=True),
            ),
            (
                "Avatar.The.Way.of.Water.2022.2160p.WEB-DL.HEVC.DV.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=(None, U), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Interstellar.2014.2160p.UHD.BluRay.x265.10bit.HDR10.DTS-HD.MA.5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(10, E), profile=("Main10", IH), hdr=("hdr10", E), audio="dtshd", channels="5.1"),
            ),
            (
                "The.Matrix.1999.2160p.UHD.BluRay.HEVC.DV.HDR.TrueHD.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr", E), bit=(10, IH), profile=("Main10", IH), audio="truehd", atmos=True),
            ),
            (
                "Chernobyl.S01E05.2160p.BluRay.HEVC.HDR10.DTS-HD.MA.5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="dtshd", channels="5.1"),
            ),
            (
                "Andor.S02E01.2160p.DSNP.WEB-DL.H265.DV.HDR10.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "The.Bear.S04E01.2160p.DSNP.WEB-DL.H265.HDR10.DDP5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1"),
            ),
            (
                "House.of.the.Dragon.S02E08.2160p.MAX.WEB-DL.H265.DV.HDR.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Shogun.S01E10.2160p.DSNP.WEB-DL.H265.HDR10.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Mr.Robot.S04E13.1080p.BluRay.x264.DTS.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="dts"),
            ),
            (
                "Better.Call.Saul.S06E13.1080p.NF.WEB-DL.H264.DDP5.1.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="eac3", channels="5.1"),
            ),
            (
                "The.Mandalorian.S03E08.2160p.DSNP.WEB-DL.H265.DV.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, bit=(10, IH), profile=("Main10", IH), hdr=(None, U), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Fallout.S01E01.2160p.AMZN.WEB-DL.H265.HDR10+.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10+", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Reacher.S03E01.2160p.AMZN.WEB-DL.H265.HDR10.DDP5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1"),
            ),
            (
                "Silo.S02E10.2160p.ATVP.WEB-DL.H265.DV.HDR10.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "foundation.s03e01.2160p.atvp.web-dl.h265.dv.hdr.ddp5.1.atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, hdr=("hdr", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "DUNE_PART_TWO_2024_2160P_HEVC_10BIT_HDR10_DDP5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(10, E), profile=("Main10", IH), hdr=("hdr10", E), audio="eac3", channels="5.1"),
            ),
            (
                "The-Batman-2022-1080p-H264-AAC5.1.mp4",
                dict(resolution=("1080p", E), codec=("avc", E), audio="aac", channels="5.1"),
            ),
            (
                "Blade Runner 2049 (2017) [2160p] [HEVC] [10bit] [HDR10] [TrueHD 7.1].mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(10, E), hdr=("hdr10", E), profile=("Main10", IH), audio="truehd", channels="7.1"),
            ),
            (
                "Tenet.2020.2160p.H264.10bit.HDR10.mkv",
                dict(resolution=("2160p", E), codec=("avc", E), bit=(10, E), hdr=("hdr10", E), profile=(None, U)),
            ),
            (
                "Foundation.S03E02.2160p.AV1.DV.HDR10.mkv",
                dict(resolution=("2160p", E), codec=("av1", E), dv=True, hdr=("hdr10", E), profile=(None, U), conflicts=True),
            ),
            (
                "Alien.Romulus.2024.2160p.H265.8bit.HDR10.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(8, E), hdr=("hdr10", E), profile=(None, U), conflicts=True),
            ),
            (
                "The.Expanse.S06E06.1080p.x264.10bit.HDR.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), bit=(10, E), hdr=("hdr", E), profile=(None, U)),
            ),
            (
                "The.Witcher.S03E08.1080p.H265.Main.10bit.mkv",
                dict(resolution=("1080p", E), codec=("hevc", E), profile=("Main", E), bit=(10, E), conflicts=True),
            ),
            (
                "Wednesday.S02E01.2160p.HEVC.Main10.8bit.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), profile=("Main10", E), bit=(8, E), conflicts=True),
            ),
            (
                "The.10th.Kingdom.S01E01.1080p.H264.AAC.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="aac", bit=(None, U)),
            ),
            (
                "8.Mile.2002.1080p.BluRay.x264.DTS.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="dts", bit=(None, U)),
            ),
            (
                "The.Hateful.Eight.2015.2160p.HEVC.HDR10.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH)),
            ),
            (
                "Bit.2024.1080p.WEB-DL.H264.AAC.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), audio="aac", bit=(None, U)),
            ),
            (
                "[2160p][HEVC][HDR10][DDP5.1].mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), hdr=("hdr10", E), bit=(10, IH), profile=("Main10", IH), audio="eac3", channels="5.1"),
            ),
            (
                "2160p60.H265.10bit.HDR10.mkv",
                dict(resolution=("2160p", E), fps=60, codec=("hevc", E), bit=(10, E), profile=("Main10", IH), hdr=("hdr10", E)),
            ),
            (
                "2160p59.94.HEVC.10bit.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), fps=59.94, bit=(10, E), profile=("Main10", IH), hdr=(None, U)),
            ),
            (
                "1080p23.976.x264.AAC2.0.mkv",
                dict(resolution=("1080p", E), codec=("avc", E), fps=23.976, audio="aac", channels="2.0"),
            ),
            (
                "1920x1080.HEVC.25fps.10bit.mkv",
                dict(width=1920, height=1080, resolution=("1080p", E), codec=("hevc", E), fps=25, bit=(10, E), profile=("Main10", IH)),
            ),
            (
                "3840x2160.AV1.60fps.10bit.HDR10.mkv",
                dict(width=3840, height=2160, resolution=("2160p", E), codec=("av1", E), fps=60, bit=(10, E), hdr=("hdr10", E), profile=(None, U)),
            ),
            (
                "John.Wick.Chapter.4.2023.2160p.UHD.BluRay.REMUX.HEVC.TrueHD.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(None, U), profile=(None, U), audio="truehd", atmos=True),
            ),
            (
                "Spider-Man.No.Way.Home.2021.2160p.WEB-DL.DV.HDR.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), dv=True, hdr=("hdr", E), codec=(None, U), bit=(10, IH), profile=(None, U), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "The.Dark.Knight.2008.2160p.UHD.BluRay.HDR10.TrueHD.5.1.mkv",
                dict(resolution=("2160p", E), hdr=("hdr10", E), codec=(None, U), bit=(10, IH), profile=(None, U), audio="truehd", channels="5.1"),
            ),
            (
                "Succession.S04E10.2160p.MAX.WEB-DL.DDP5.1.mkv",
                dict(resolution=("2160p", E), codec=(None, U), audio="eac3", channels="5.1", bit=(None, U), profile=(None, U)),
            ),
            (
                "Game.of.Thrones.S08E06.2160p.UHD.BluRay.HEVC.DV.TrueHD.Atmos.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), dv=True, bit=(10, IH), profile=("Main10", IH), audio="truehd", atmos=True),
            ),
            (
                "For.All.Mankind.S04E10.2160p.ATVP.WEB-DL.DV.DDP5.1.Atmos.mkv",
                dict(resolution=("2160p", E), dv=True, codec=(None, U), bit=(10, IH), profile=(None, U), audio="eac3", channels="5.1", atmos=True),
            ),
            (
                "Random.Release.2160p.x265.DDP5.1.mkv",
                dict(resolution=("2160p", E), codec=("hevc", E), bit=(None, U), profile=(None, U), audio="eac3", channels="5.1"),
            ),
            (
                "Random.Release.2160p.HDR10.DDP5.1.mkv",
                dict(resolution=("2160p", E), hdr=("hdr10", E), bit=(10, IH), codec=(None, U), profile=(None, U), audio="eac3", channels="5.1"),
            ),
            (
                "Random.Release.DV.DDP5.1.mkv",
                dict(dv=True, bit=(10, IH), resolution=(None, U), codec=(None, U), profile=(None, U), audio="eac3", channels="5.1"),
            ),
            (
                "Random.Release.10bit.mkv",
                dict(bit=(10, E), resolution=(None, U), codec=(None, U), profile=(None, U)),
            ),
        ]
        self.assertEqual(len(cases), 100)
        for filename, expected in cases:
            with self.subTest(filename=filename):
                _check(filename, **expected)

    def test_explicit_wins_over_inference(self):
        parsed = parse_filename("2160p.HEVC.Main.10bit.mkv")
        self.assertEqual(parsed.profile.value, "Main")
        self.assertEqual(parsed.bit_depth.value, 10)
        self.assertTrue(parsed.conflicts)

    def test_do_not_invent_hevc_from_dv_alone(self):
        parsed = parse_filename("Movie.DV.mkv")
        self.assertEqual(parsed.codec.source, "unknown")
        self.assertNotEqual(parsed.profile.value, "Main10")
        self.assertEqual(parsed.bit_depth.value, 10)
        self.assertEqual(parsed.bit_depth.source, "inferred_high")


if __name__ == "__main__":
    unittest.main()
