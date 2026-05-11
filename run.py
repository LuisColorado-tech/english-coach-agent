#!/usr/bin/env python3
"""
English Coach Agent (ECA-1) — Entry Point.

Usage:
    python run.py              # Start agent with microphone
    python run.py --text       # Start in text mode (no mic, send via API)
    python run.py --setup      # Run setup wizard
    python run.py --test       # Run self-test
"""

import argparse
import asyncio
import signal
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from config.logging_config import setup_logging
from config.settings import DATA_DIR

logger = setup_logging()


def parse_args():
    parser = argparse.ArgumentParser(
        description="English Coach Agent — AI English conversation practice",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                Start interactive voice practice
  python run.py --text         Text mode (type instead of speak)
  python run.py --setup        Run initial setup wizard
  python run.py --test         Verify components are working
        """,
    )

    parser.add_argument(
        "--text", action="store_true",
        help="Run in text-only mode (no microphone)",
    )
    parser.add_argument(
        "--setup", action="store_true",
        help="Run the setup wizard",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run self-diagnostic tests",
    )
    parser.add_argument(
        "--no-mic", action="store_true",
        help="Start agent without microphone (for UI-driven input)",
    )
    parser.add_argument(
        "--gui", action="store_true",
        help="Launch with graphical interface (default on Windows)",
    )
    parser.add_argument(
        "--no-gui", action="store_true",
        help="Run without graphical interface (headless mode)",
    )

    return parser.parse_args()


async def run_text_mode():
    """Text-only mode: type to the agent, read responses."""
    from core.agent import EnglishCoachAgent

    agent = EnglishCoachAgent()
    await agent.initialize()

    print("\n=== English Coach Agent — Text Mode ===")
    print("Type your message and press Enter. Type /quit to exit.\n")

    # Start the pipeline (non-microphone)
    asyncio.create_task(agent.start(use_microphone=False))

    await asyncio.sleep(1)  # Give pipeline time to start

    while agent.is_running:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("You: ")
            )

            if not user_input.strip():
                continue

            if user_input.lower() in ("/quit", "/exit", "/q"):
                break

            result = await agent.send_text(user_input)
            if result:
                print(f"Aria: {result.agent_text}")
                if result.corrections:
                    print("\n--- Corrections ---")
                    for c in result.corrections:
                        print(f"  '{c.original}' → '{c.corrected}' ({c.explanation})")
                print()

        except (KeyboardInterrupt, EOFError):
            break

    await agent.stop()
    print("\nGoodbye!")


async def run_test():
    """Run self-diagnostics to verify components work."""
    print("=== English Coach Agent — Self Test ===\n")

    results = []

    # Test 1: Config loading
    try:
        from config.settings import DEEPSEEK_API_KEY, DATA_DIR
        print(f"[{'PASS' if DATA_DIR else 'FAIL'}] Config loaded (data_dir={DATA_DIR})")
        results.append(True)
    except Exception as e:
        print(f"[FAIL] Config loading: {e}")
        results.append(False)

    # Test 2: DeepSeek API connectivity
    try:
        from llm.deepseek_client import DeepSeekClient
        client = DeepSeekClient()
        if DEEPSEEK_API_KEY:
            await client.initialize()
            response = await client.chat("Hello! Say 'test successful' in one word.")
            assert "test" in response.content.lower() or "success" in response.content.lower()
            print(f"[PASS] DeepSeek API: {response.content[:80]}")
            results.append(True)
        else:
            print("[SKIP] DeepSeek API: DEEPSEEK_API_KEY not set")
            results.append(None)
    except Exception as e:
        print(f"[FAIL] DeepSeek API: {e}")
        results.append(False)

    # Test 3: edge-tts
    try:
        from tts.edge_tts_handler import EdgeTTSService
        tts = EdgeTTSService()
        audio = await tts.synthesize("Test successful")
        if audio and len(audio) > 0:
            print(f"[PASS] edge-tts: {len(audio)} bytes synthesized")
            results.append(True)
        else:
            print("[FAIL] edge-tts: No audio produced")
            results.append(False)
    except Exception as e:
        print(f"[FAIL] edge-tts: {e}")
        results.append(False)

    # Test 4: Response processor
    try:
        from llm.response_processor import ResponseProcessor, Correction

        processor = ResponseProcessor()
        test_text = (
            "Actually, it's 'I went to the store'. "
            "[CORRECTION: original='I goed to the store' corrected='I went to the store' "
            "type='grammar' explanation='The past tense of go is went, not goed'] "
            "Anyway, that sounds fun!"
        )
        result = processor.process(test_text)
        assert len(result.corrections) == 1
        assert result.corrections[0].original == "I goed to the store"
        assert "I went to the store" in result.corrections[0].corrected
        print(f"[PASS] Response processor: {len(result.corrections)} correction(s) parsed")
        results.append(True)
    except Exception as e:
        print(f"[FAIL] Response processor: {e}")
        results.append(False)

    # Test 5: VAD handler
    try:
        from stt.vad_handler import SileroVADHandler, VADConfig
        import numpy as np

        vad = SileroVADHandler(VADConfig())
        await vad.initialize()

        # Send some silence (zeros)
        silence = np.zeros(480, dtype=np.float32)  # 480 samples @ 16kHz = 30ms
        state = await vad.process_audio(silence)
        assert not vad.is_speaking

        print(f"[PASS] VAD handler: initialized, state={state.name}")
        results.append(True)
    except Exception as e:
        print(f"[FAIL] VAD handler: {e}")
        results.append(False)

    # Summary
    actual_results = [r for r in results if r is not None]
    passed = sum(1 for r in actual_results if r)
    total = len(actual_results)
    skipped = len([r for r in results if r is None])

    print(f"\n=== Results: {passed}/{total} passed, {skipped} skipped ===")
    return passed == total


def run_setup():
    """Run the setup wizard."""
    from setup import main as setup_main
    setup_main()


async def run_gui_mode(use_mic: bool = True):
    """Launch the agent with graphical interface."""
    import threading

    from core.agent import EnglishCoachAgent
    from ui.main_window import MainWindow

    agent = EnglishCoachAgent()

    # Create main window
    window = MainWindow(agent)

    # Wire UI to agent events
    agent.on("on_state_change", lambda new, old: window.schedule_update(
        window.update_state, new
    ))
    agent.on("on_transcription", lambda text: window.schedule_update(
        window.update_transcription, text
    ))
    agent.on("on_response", lambda processed: window.schedule_update(
        window.update_response, processed
    ))
    agent.on("on_correction", lambda correction: window.schedule_update(
        window.update_correction, correction
    ))
    agent.on("on_turn_complete", lambda result: window.schedule_update(
        window.update_turn, result
    ))
    agent.on("on_error", lambda msg: window.schedule_update(
        window.show_error, msg
    ))

    # Update profile in sidebar after init
    async def update_profile_display():
        await asyncio.sleep(1)  # Give agent time to init
        try:
            profile = agent.get_profile()
            window.schedule_update(window.update_profile, profile)
        except Exception:
            pass

    # Start the agent in background
    agent_task = asyncio.create_task(agent.start(use_microphone=use_mic))

    # Show profile in sidebar
    asyncio.create_task(update_profile_display())

    # Start session timer
    window.schedule_update(window._start_timer)

    # Start tray icon in a separate thread
    try:
        from ui.tray_icon import TrayIcon

        tray = TrayIcon(window, agent)

        def start_tray():
            tray.start()

        tray_thread = threading.Thread(target=start_tray, daemon=True)
        tray_thread.start()
    except Exception as e:
        logger.warning(f"Tray icon unavailable: {e}")

    # Run the UI main loop (this blocks)
    window.start()

    # Cleanup when UI closes
    await agent.stop()
    agent_task.cancel()


async def run_headless_mode(use_mic: bool = True):
    """Launch agent without UI (console only)."""
    from core.agent import EnglishCoachAgent

    agent = EnglishCoachAgent()

    def shutdown_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(agent.stop())

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print("\n" + "=" * 50)
    print("  English Coach Agent (ECA-1)")
    print("  AI English Conversation Practice")
    print("=" * 50)
    print()
    print("Press Ctrl+C to exit")
    print()

    try:
        await agent.start(use_microphone=use_mic)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await agent.stop()

    print("\nAgent stopped. Goodbye!\n")


async def main():
    args = parse_args()

    if args.setup:
        run_setup()
        return

    if args.test:
        success = await run_test()
        sys.exit(0 if success else 1)

    if args.text:
        await run_text_mode()
        return

    # Determine mode
    use_mic = not args.no_mic
    use_gui = args.gui or (not args.no_gui and sys.platform == "win32")

    if use_gui:
        await run_gui_mode(use_mic=use_mic)
    else:
        await run_headless_mode(use_mic=use_mic)


if __name__ == "__main__":
    asyncio.run(main())
