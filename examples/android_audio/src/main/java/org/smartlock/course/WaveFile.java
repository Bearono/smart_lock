package org.smartlock.course;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

/** Strict, bounded 48 kHz mono PCM16 RIFF/WAVE interchange. */
public final class WaveFile {
    public static final int RATE = 48000;
    public static final int MAX_SAMPLES = RATE * 10;
    public static final int MAX_BYTES = MAX_SAMPLES * 2 + 1024;
    private WaveFile() { }

    public static byte[] readBounded(InputStream input, int maximum) throws IOException {
        if (input == null) throw new IOException("无法读取文件");
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = input.read(buffer)) != -1) {
            if (output.size() + count > maximum) throw new IOException("文件超过允许大小");
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    public static double[] decode(byte[] bytes) {
        if (bytes == null || bytes.length < 44 || bytes.length > MAX_BYTES
                || !tag(bytes, 0, "RIFF") || !tag(bytes, 8, "WAVE")) fail();
        ByteBuffer data = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        long end = Integer.toUnsignedLong(data.getInt(4)) + 8;
        if (end != bytes.length) fail();
        boolean format = false;
        int sampleOffset = -1, sampleBytes = 0;
        for (long offset = 12; offset < end;) {
            if (offset + 8 > end) fail();
            int index = (int) offset;
            long size = Integer.toUnsignedLong(data.getInt(index + 4));
            long next = offset + 8 + size + (size & 1);
            if (next > end) fail();
            if (tag(bytes, index, "fmt ")) {
                if (format || size < 16 || data.getShort(index + 8) != 1
                        || data.getShort(index + 10) != 1 || data.getInt(index + 12) != RATE
                        || data.getInt(index + 16) != RATE * 2 || data.getShort(index + 20) != 2
                        || data.getShort(index + 22) != 16) fail();
                format = true;
            } else if (tag(bytes, index, "data")) {
                if (!format || sampleOffset >= 0 || size % 2 != 0 || size > MAX_SAMPLES * 2) fail();
                sampleOffset = index + 8;
                sampleBytes = (int) size;
            }
            offset = next;
        }
        if (!format || sampleOffset < 0 || sampleBytes == 0) fail();
        double[] samples = new double[sampleBytes / 2];
        for (int i = 0; i < samples.length; i++) samples[i] = data.getShort(sampleOffset + i * 2) / 32767.0;
        return samples;
    }

    public static byte[] encode(double[] samples) {
        if (samples == null || samples.length == 0 || samples.length > MAX_SAMPLES) fail();
        ByteBuffer result = ByteBuffer.allocate(44 + samples.length * 2).order(ByteOrder.LITTLE_ENDIAN);
        result.put("RIFF".getBytes(StandardCharsets.US_ASCII)).putInt(result.capacity() - 8);
        result.put("WAVEfmt ".getBytes(StandardCharsets.US_ASCII)).putInt(16).putShort((short) 1)
                .putShort((short) 1).putInt(RATE).putInt(RATE * 2).putShort((short) 2).putShort((short) 16);
        result.put("data".getBytes(StandardCharsets.US_ASCII)).putInt(samples.length * 2);
        for (double sample : samples) {
            if (!Double.isFinite(sample) || Math.abs(sample) > 1) fail();
            result.putShort((short) Math.rint(sample * 32767));
        }
        return result.array();
    }

    private static boolean tag(byte[] value, int index, String tag) {
        for (int i = 0; i < 4; i++) if (value[index + i] != tag.charAt(i)) return false;
        return true;
    }
    private static void fail() { throw new IllegalArgumentException("需要不超过 10 秒的 48 kHz、单声道、16 位 PCM WAV"); }
}
