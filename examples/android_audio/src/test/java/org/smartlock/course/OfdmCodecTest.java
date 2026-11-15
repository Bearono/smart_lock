package org.smartlock.course;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.Arrays;
import java.util.Random;

public class OfdmCodecTest {
    @Test public void legacyWavesRemainReadableAndRobustFramesAreBounded() {
        byte[] payload = new byte[128];new Random(913).nextBytes(payload);
        assertArrayEquals(payload, OfdmCodec.decode(OfdmCodec.encodeLegacy(payload)));
        assertTrue(OfdmCodec.encode(new byte[2048]).length <= WaveFile.MAX_SAMPLES);
    }
    @Test public void binaryRoundtripAcrossBounds() {
        for (int size : new int[] {1, 5, 8, 127, 256, 2048}) {
            byte[] original = new byte[size];
            new Random(size).nextBytes(original);
            assertArrayEquals(original, OfdmCodec.decode(WaveFile.decode(WaveFile.encode(OfdmCodec.encode(original)))));
        }
    }
    @Test public void delayNoisePolarityAndMultipath() {
        byte[] payload = new byte[128]; new Random(42).nextBytes(payload);
        double[] original = OfdmCodec.encode(payload);
        double[] recording = new double[original.length + 273 + 137 + 8];
        Random noise = new Random(42);
        for (int i = 0; i < original.length + 8; i++) {
            double direct = i < original.length ? original[i] * 0.7 : 0;
            double echo = i >= 8 && i - 8 < original.length ? original[i - 8] * 0.15 : 0;
            recording[i + 273] = -(direct + echo + noise.nextGaussian() * 0.002) * 0.5;
        }
        assertArrayEquals(payload, OfdmCodec.decode(recording));
    }
    @Test public void malformedInputIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> OfdmCodec.encode(new byte[0]));
        assertThrows(IllegalArgumentException.class, () -> OfdmCodec.encode(new byte[2049]));
        assertThrows(IllegalArgumentException.class, () -> OfdmCodec.decode(new double[700]));
        assertThrows(IllegalArgumentException.class, () -> OfdmCodec.decode(new double[480001]));
        assertThrows(IllegalArgumentException.class, () -> OfdmCodec.decode(new double[3000]));
        double[] nan = new double[3000]; nan[0] = Double.NaN;
        assertThrows(IllegalArgumentException.class, () -> OfdmCodec.decode(nan));
        double[] corrupt = OfdmCodec.encode(new byte[256]);
        Random noise = new Random(1);
        for (int i = 1000; i < 2000; i++) corrupt[i] = noise.nextGaussian() * 0.3;
        assertThrows(IllegalArgumentException.class, () -> OfdmCodec.decode(corrupt));
    }
    @Test public void waveFormatAndTruncationAreChecked() {
        byte[] valid = WaveFile.encode(OfdmCodec.encode(new byte[] {1,2,3}));
        assertThrows(IllegalArgumentException.class, () -> WaveFile.decode(Arrays.copyOf(valid, valid.length - 1)));
        byte[] stereo = valid.clone(); stereo[22] = 2;
        assertThrows(IllegalArgumentException.class, () -> WaveFile.decode(stereo));
        byte[] badRate = valid.clone(); badRate[24] = 0;
        assertThrows(IllegalArgumentException.class, () -> WaveFile.decode(badRate));
        byte[] oversizedChunk = valid.clone(); Arrays.fill(oversizedChunk, 40, 44, (byte) 255);
        assertThrows(IllegalArgumentException.class, () -> WaveFile.decode(oversizedChunk));
        assertThrows(IllegalArgumentException.class, () -> WaveFile.encode(new double[] {2}));
    }
}
