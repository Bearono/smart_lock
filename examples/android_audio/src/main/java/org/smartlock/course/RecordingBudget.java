package org.smartlock.course;

/** Both wall-clock time and sample count bound a capture, including a silent driver. */
public final class RecordingBudget {
    private final long started;
    public RecordingBudget(long monotonicMillis) { started = monotonicMillis; }
    public boolean canRead(long now, int samples) {
        return now >= started && now - started < 10_000
                && samples >= 0 && samples < WaveFile.MAX_SAMPLES;
    }
}
