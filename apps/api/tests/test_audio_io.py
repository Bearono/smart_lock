"""Audio resource/timeout tests using a fake PortAudio backend; never opens hardware."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import numpy as np

from smartlock_protocol.audio import RATE, read_wav, wav_bytes

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('audio_io_under_test', ROOT / 'deploy/audio_device.py')
audio_io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio_io)


class ImmediateEvent:
    def __init__(self):
        self.done = False

    def set(self):
        self.done = True

    def wait(self, timeout=None):
        return self.done


class FakeBackend:
    class CallbackStop(Exception):
        pass

    class CallbackAbort(Exception):
        pass

    def __init__(self, mode='normal'):
        self.mode = mode
        self.calls = []
        self.output = []

    def check_input_settings(self, **kwargs):
        self.calls.append('check_input')

    def check_output_settings(self, **kwargs):
        self.calls.append('check_output')

    def InputStream(self, **kwargs):
        return FakeStream(self, True, kwargs)

    def OutputStream(self, **kwargs):
        return FakeStream(self, False, kwargs)


class FakeStream:
    def __init__(self, backend, recording, settings):
        self.backend, self.recording, self.settings = backend, recording, settings
        backend.calls.append('created')

    def start(self):
        backend = self.backend
        backend.calls.append('start')
        if backend.mode == 'start_error':
            raise RuntimeError('Device disappeared before stream start')
        if backend.mode == 'stalled':
            return
        finished = self.settings.get('finished_callback', lambda: None)
        if backend.mode == 'early_finish':
            finished()
            return
        count = self.settings['blocksize']
        for _ in range(1000):
            buffer = (np.full((count, 1), 16384, dtype=np.int16) if self.recording
                      else np.full((count, 1), np.nan, dtype=np.float32))
            status = 'input overflow' if backend.mode == 'status_error' else ''
            try:
                self.settings['callback'](buffer, count, None, status)
            except (backend.CallbackStop, backend.CallbackAbort):
                if not self.recording:
                    backend.output.append(buffer.copy())
                finished()
                return
            if not self.recording:
                backend.output.append(buffer.copy())
            if backend.mode == 'partial_finish':
                finished()
                return
        raise AssertionError('Fake stream failed to terminate')

    def stop(self):
        self.backend.calls.append('stop')

    def abort(self):
        self.backend.calls.append('abort')

    def close(self):
        self.backend.calls.append('close')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
        self.close()


class AudioIOTests(unittest.TestCase):
    def setUp(self):
        self.event_patch = patch('threading.Event', ImmediateEvent)
        self.event_patch.start()
        self.addCleanup(self.event_patch.stop)

    def test_windows_com_is_balanced_on_success_and_stream_failure(self):
        for status in (0, 1):
            ole = Mock()
            ole.CoInitializeEx.return_value = status
            with patch.object(audio_io.sys, 'platform', 'win32'), patch('ctypes.WinDLL', return_value=ole, create=True):
                with self.assertRaisesRegex(RuntimeError, 'fixture'):
                    with audio_io._audio_thread():
                        raise RuntimeError('fixture')
            ole.CoInitializeEx.assert_called_once_with(None, 0)
            ole.CoUninitialize.assert_called_once_with()

    def test_windows_com_respects_existing_sta_and_rejects_initialization_errors(self):
        ole = Mock()
        with patch.object(audio_io.sys, 'platform', 'win32'), patch('ctypes.WinDLL', return_value=ole, create=True):
            ole.CoInitializeEx.return_value = -2147417850  # RPC_E_CHANGED_MODE
            with audio_io._audio_thread():
                pass
            ole.CoUninitialize.assert_not_called()
            ole.CoInitializeEx.return_value = -2147024882  # E_OUTOFMEMORY
            with self.assertRaisesRegex(RuntimeError, 'COM initialization failed'):
                with audio_io._audio_thread():
                    self.fail('Cannot open audio after failed initialization')
            ole.CoUninitialize.assert_not_called()

    def test_raw_microphone_requires_wasapi_and_does_not_silently_fall_back(self):
        backend = Mock()
        backend.query_devices.return_value = {'hostapi': 2}
        backend.query_hostapis.return_value = {'name': 'MME'}
        with patch.object(audio_io.sys, 'platform', 'win32'):
            with self.assertRaisesRegex(ValueError, 'WASAPI'):
                audio_io._input_options(backend, 12, True)
            backend.query_hostapis.return_value = {'name': 'Windows WASAPI'}
            backend._lib.eStreamOptionRaw = 1
            settings = backend.WasapiSettings.return_value
            options = audio_io._input_options(backend, 12, True)
            self.assertIs(options['extra_settings'], settings)
            self.assertEqual(settings._streaminfo.streamOption, 1)
        backend.InputStream.assert_not_called()

    def test_capture_exact_frame_count_and_closes_stream(self):
        backend = FakeBackend()
        recorded = audio_io.record(0.1, 3, backend=backend)
        values = read_wav(recorded)
        self.assertEqual(len(values), int(RATE * 0.1))
        self.assertTrue(np.all(values > 0.49))
        self.assertEqual(backend.calls[-1], 'close')

    def test_playback_preserves_samples_applies_gain_and_zero_pads_tail(self):
        backend = FakeBackend()
        original = np.linspace(-0.5, 0.5, 1500)
        wave = wav_bytes(original)
        audio_io.play(wave, 4, gain=0.2, backend=backend)
        output = np.concatenate(backend.output)[:, 0]
        np.testing.assert_allclose(output[:1500], read_wav(wave) * 0.2, atol=1e-7)
        self.assertTrue(np.all(output[1500:] == 0))
        self.assertEqual(backend.calls[-1], 'close')

    def test_capture_callback_status_error_is_reported_and_closed(self):
        backend = FakeBackend('status_error')
        with self.assertRaises(RuntimeError):
            audio_io.record(0.1, 3, backend=backend)
        self.assertEqual(backend.calls[-1], 'close')

    def test_playback_callback_status_error_is_reported_and_closed(self):
        backend = FakeBackend('status_error')
        with self.assertRaises(RuntimeError):
            audio_io.play(wav_bytes(np.zeros(1500)), 4, backend=backend)
        self.assertEqual(backend.calls[-1], 'close')

    def test_early_output_finish_cannot_report_success(self):
        for mode in ('early_finish', 'partial_finish'):
            with self.subTest(mode=mode):
                backend = FakeBackend(mode)
                with self.assertRaises(RuntimeError):
                    audio_io.play(wav_bytes(np.zeros(3000)), 4, backend=backend)
                self.assertEqual(backend.calls[-1], 'close')

    def test_stalled_output_is_aborted_before_close(self):
        backend = FakeBackend('stalled')
        with self.assertRaises(RuntimeError):
            audio_io.play(wav_bytes(np.zeros(3000)), 4, backend=backend)
        self.assertIn('abort', backend.calls)
        self.assertLess(backend.calls.index('abort'), backend.calls.index('close'))

    def test_stream_start_failure_still_closes_handle(self):
        for recording in (True, False):
            with self.subTest(recording=recording):
                backend = FakeBackend('start_error')
                with self.assertRaises(RuntimeError):
                    if recording:
                        audio_io.record(0.1, 3, backend=backend)
                    else:
                        audio_io.play(wav_bytes(np.zeros(3000)), 4, backend=backend)
                self.assertEqual(backend.calls[-1], 'close')


if __name__ == '__main__':
    unittest.main()
