"""Pi entrypoint. Load selected detector ONCE, log backend+path, run.

Switching backends = change DETECTOR_BACKEND in .env only.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "config"))

from settings import load_settings, log_active_config  # noqa: E402

from detector_api import DetectorConfigError, create_detector  # noqa: E402


def main() -> int:
    settings = load_settings()
    log_active_config(settings)
    try:
        detector = create_detector(settings)
    except DetectorConfigError as e:
        print(f"[pi] FATAL: {e}", flush=True)
        return 2
    print(f"[pi] loaded backend={detector.backend_name} "
          f"model={detector.model_path} imgsz={detector.imgsz} "
          f"conf={detector.conf} classes={len(detector.class_names)}",
          flush=True)

    if not settings.junction_id or not settings.device_api_key:
        print("[pi] WARNING: JUNCTION_ID/DEVICE_API_KEY unset — "
              "cloud upload disabled, local control continues", flush=True)
        return 0

    from cloud import CloudClient  # noqa: E402
    from controller import AdaptiveController  # noqa: E402

    cloud = CloudClient(settings)
    cloud.start_mqtt()
    cloud.start_poll_fallback()
    ctl = AdaptiveController()
    print(f"[pi] running junction={settings.junction_id} "
          f"(mqtt primary + http poll every {settings.command_poll_interval_s}s)",
          flush=True)
    try:
        while True:
            for cmd in cloud.drain():
                print(f"[pi] command {cmd.type} approach={cmd.approach}", flush=True)
                if cmd.type in ("PRIORITY_REQUEST", "FORCE_RELEASE"):
                    ctl.hold_green(cmd.approach)
                    cloud.ack(cmd.id)
                elif cmd.type in ("RELEASE_PRIORITY", "CANCEL", "HOLD"):
                    ctl.release_override()
                    cloud.ack(cmd.id)
            cloud.send_heartbeat()
            time.sleep(settings.heartbeat_interval_s)
    except KeyboardInterrupt:
        pass
    finally:
        cloud.stop()
        detector.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
