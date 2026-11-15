import java.nio.file.Files;
import java.nio.file.Path;
import org.smartlock.course.OfdmCodec;
import org.smartlock.course.WaveFile;

/** CLI fixture for bidirectional Python/Java protocol validation. */
public final class CodecInterop {
    public static void main(String[] args) throws Exception {
        if (args.length != 3 || !(args[0].equals("encode") || args[0].equals("decode")))
            throw new IllegalArgumentException("encode|decode INPUT OUTPUT");
        byte[] input = Files.readAllBytes(Path.of(args[1]));
        byte[] result = args[0].equals("encode") ? WaveFile.encode(OfdmCodec.encode(input))
                : OfdmCodec.decode(WaveFile.decode(input));
        Files.write(Path.of(args[2]), result);
    }
}
