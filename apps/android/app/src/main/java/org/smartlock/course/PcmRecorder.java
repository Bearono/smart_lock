package org.smartlock.course;

import android.Manifest;
import android.annotation.SuppressLint;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.SystemClock;
import java.util.Arrays;

/** Foreground-only, user-started recording. The caller stops it in onStop(). */
public final class PcmRecorder {
    public interface Listener { void finished(double[] samples, String source); void failed(String message); }
    private volatile boolean running;
    private volatile boolean active;
    private volatile AudioRecord recorder;

    @SuppressLint("MissingPermission") // Explicit permission check immediately precedes creation.
    public void start(Context context, Listener listener) {
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            throw new SecurityException("请先授予麦克风权限");
        if (active) throw new IllegalStateException("录音已在进行");
        int minimum = AudioRecord.getMinBufferSize(WaveFile.RATE,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        if (minimum <= 0) throw new IllegalStateException("此设备不支持 48 kHz 单声道录音");
        AudioManager manager = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
        boolean raw = "true".equals(manager.getProperty(AudioManager.PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED));
        AudioRecord candidate = new AudioRecord(raw ? MediaRecorder.AudioSource.UNPROCESSED
                : MediaRecorder.AudioSource.VOICE_RECOGNITION, WaveFile.RATE,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(minimum * 2, 8192));
        if (candidate.getState() != AudioRecord.STATE_INITIALIZED) {
            candidate.release();
            throw new IllegalStateException("麦克风初始化失败");
        }
        try { candidate.startRecording(); }
        catch (RuntimeException error) { candidate.release(); throw error; }
        recorder = candidate;
        running = true;
        active = true;
        final RecordingBudget budget = new RecordingBudget(SystemClock.elapsedRealtime());
        new Thread(() -> {
            double[] values = new double[WaveFile.MAX_SAMPLES];
            short[] buffer = new short[2048];
            int total = 0;
            String failure = null;
            try {
                while (running && budget.canRead(SystemClock.elapsedRealtime(), total)) {
                    int count = candidate.read(buffer, 0, Math.min(buffer.length, values.length - total), AudioRecord.READ_NON_BLOCKING);
                    if (count < 0) {
                        if (!running) break;
                        throw new IllegalStateException("麦克风读取失败：" + count);
                    }
                    if (count == 0) {
                        try { Thread.sleep(5); }
                        catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); break; }
                        continue;
                    }
                    for (int i = 0; i < count; i++) values[total++] = Math.max(-32767, buffer[i]) / 32767.0;
                }
            } catch (RuntimeException error) { failure = error.getMessage(); }
            finally {
                running = false;
                try { candidate.stop(); } catch (IllegalStateException ignored) { }
                candidate.release();
                recorder = null;
                active = false;
            }
            if (failure != null) listener.failed(failure);
            else if (total == 0) listener.failed("没有采集到音频");
            else listener.finished(Arrays.copyOf(values, total), raw ? "UNPROCESSED" : "VOICE_RECOGNITION（设备不支持原始输入）");
        }, "smartlock-audio-record").start();
    }

    public boolean isRunning() { return active; }
    public void stop() {
        running = false;
        AudioRecord current = recorder;
        if (current != null) try { current.stop(); } catch (IllegalStateException ignored) { }
    }
}
