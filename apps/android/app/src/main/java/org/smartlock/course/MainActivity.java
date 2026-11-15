package org.smartlock.course;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;
import java.nio.ByteBuffer;
import java.util.Base64;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int PICK_WAV = 1, PICK_PAYLOAD = 2, SAVE_FILE = 3, MIC_PERMISSION = 4, PICK_ISSUER = 5;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final PcmRecorder recorder = new PcmRecorder();
    private final D2dCrypto crypto = new D2dCrypto();
    private FrameLayout content;
    private LinearLayout connectPage, audioPage;
    private ScrollView audioScroll, connectScroll;
    private TextView connectionStatus, audioStatus;
    private EditText endpoint;
    private EditText issuer, recipient, issuerPin, message;
    private TextView pinFingerprint;
    private CheckBox pinVerified;
    private WebView web;
    private OriginPolicy policy;
    private MediaPlayer player;
    private byte[] wave, payload, exportBytes;
    private byte[] recipientPublicDer;
    private boolean busy, destroyed;
    private String page = "connect";

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        LinearLayout root = column();
        root.setBackgroundColor(Color.rgb(249, 246, 240));
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets edges = insets.getInsets(android.view.WindowInsets.Type.systemBars());
                view.setPadding(edges.left, edges.top, edges.right, edges.bottom);
                return insets;
            });
        } else root.setFitsSystemWindows(true);
        TextView title = text("SmartLock", 24);
        title.setPadding(dp(18), dp(12), dp(18), dp(4));
        root.addView(title);
        LinearLayout navigation = new LinearLayout(this);
        for (String[] item : new String[][] {{"门锁", "web"}, {"音频实验", "audio"}, {"连接", "connect"}}) {
            Button button = button(item[0], () -> show(item[1]));
            navigation.addView(button, new LinearLayout.LayoutParams(0, dp(52), 1));
        }
        root.addView(navigation);
        connectionStatus = text("尚未连接服务", 13);
        connectionStatus.setPadding(dp(18), dp(4), dp(18), dp(8));
        root.addView(connectionStatus);
        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        buildConnectPage();
        buildAudioPage();
        setContentView(root);
        if (android.os.Build.VERSION.SDK_INT >= 33)
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::navigateBack);
        show("connect");
    }

    private void buildConnectPage() {
        connectPage = paddedColumn();
        connectPage.addView(text("连接你的门锁服务", 22));
        connectPage.addView(text("输入手机可以访问的 HTTPS 地址。电脑的 localhost 不能用于手机。首次登录按网页完成 TOTP 绑定。", 16));
        endpoint = new EditText(this);
        endpoint.setHint("https://lock.example.com:8443");
        endpoint.setSingleLine(true);
        endpoint.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        endpoint.setText(getPreferences(MODE_PRIVATE).getString("endpoint", ""));
        endpoint.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        connectPage.addView(endpoint, new LinearLayout.LayoutParams(-1, dp(56)));
        connectPage.addView(button("保存地址并连接", this::connect));
        connectPage.addView(button("清除本机网页会话", () -> new AlertDialog.Builder(this)
                .setTitle("清除本机会话？").setMessage("这会清除本机登录状态。退出账户请先使用网页中的退出功能。").setNegativeButton("取消", null)
                .setPositiveButton("清除", (dialog, which) -> clearWeb()).show()));
        connectPage.addView(text("证书错误会停止连接。调试 APK 可使用你手动安装的课程 CA；正式 APK 仅信任系统 CA。地址变化后需重新登录。", 14));
        connectScroll = scroll(connectPage);
        content.addView(connectScroll);
    }

    @SuppressLint("SetJavaScriptEnabled") // Existing Vue application; exact HTTPS origin only, no native JS bridge.
    private void connect() {
        OriginPolicy selected;
        try { selected = new OriginPolicy(endpoint.getText().toString()); }
        catch (IllegalArgumentException error) { endpoint.setError(error.getMessage()); return; }
        clearWeb();
        policy = selected;
        getPreferences(MODE_PRIVATE).edit().putString("endpoint", selected.origin()).apply();
        WebView created = new WebView(this);
        web = created;
        WebSettings settings = created.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(false);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSaveFormData(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setSafeBrowsingEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        created.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(created, false);
        created.setWebChromeClient(new WebChromeClient() {
            @Override public void onPermissionRequest(PermissionRequest request) { request.deny(); }
        });
        created.setWebViewClient(new WebViewClient() {
            private boolean mainFailed;
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                mainFailed = false;
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                boolean allowed = selected.allows(request.getUrl().toString());
                if (!allowed) connectionStatus.setText("已阻止离开已配置的 HTTPS 服务");
                return !allowed;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (selected.allows(url)) return null;
                byte[] png = OriginPolicy.inlinePng(url);
                return png == null ? new WebResourceResponse("text/plain", "UTF-8", new ByteArrayInputStream(new byte[0]))
                        : new WebResourceResponse("image/png", null, new ByteArrayInputStream(png));
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
                mainFailed = true;
                connectionStatus.setText("证书验证失败：检查课程 CA、服务地址与证书有效期");
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    mainFailed = true;
                    connectionStatus.setText("连接失败，请检查 HTTPS 地址和网络");
                }
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!mainFailed && selected.allows(url)) connectionStatus.setText(selected.origin());
            }
        });
        content.addView(created, new FrameLayout.LayoutParams(-1, -1));
        connectionStatus.setText("正在连接 " + selected.origin());
        CookieManager.getInstance().removeAllCookies(removed -> {
            if (!destroyed && web == created) created.loadUrl(selected.origin() + "/");
        });
        show("web");
    }

    private void clearWeb() {
        if (web != null) {
            web.stopLoading(); web.clearHistory(); web.clearCache(true);
            content.removeView(web); web.destroy(); web = null;
        }
        CookieManager.getInstance().removeAllCookies(null);
        connectionStatus.setText("本机会话已清除");
    }

    private void buildAudioPage() {
        audioPage = paddedColumn();
        audioPage.addView(text("OFDM 音频实验", 22));
        audioPage.addView(text("48 kHz · 单声道 · PCM16\n发送载荷最多 2048 字节，录音最多 10 秒。播放和录音均由你主动开始，离开应用立即停止。", 16));
        audioStatus = text("选择载荷生成音频，或导入 / 录制 WAV 后解码。", 16);
        audioStatus.setPadding(0, dp(14), 0, dp(14));
        audioPage.addView(audioStatus);
        audioPage.addView(button("选择载荷并生成 OFDM WAV", () -> pick(PICK_PAYLOAD)));
        audioPage.addView(button("导入 WAV", () -> pick(PICK_WAV)));
        audioPage.addView(button("播放当前 WAV", this::play));
        audioPage.addView(button("停止播放 / 录音", this::stopAudio));
        audioPage.addView(button("录音（最多 10 秒）", this::requestRecording));
        audioPage.addView(button("解码当前 WAV", this::decode));
        audioPage.addView(button("保存当前 WAV", () -> export(wave, "audio/wav", "smartlock-audio.wav")));
        audioPage.addView(button("保存当前载荷", () -> export(payload, "application/octet-stream", "smartlock-payload.bin")));
        audioPage.addView(button("分享当前 WAV", () -> share(wave, "wave.wav", "audio/wav")));
        audioPage.addView(button("分享当前载荷", () -> share(payload, "payload.bin", "application/octet-stream")));
        audioPage.addView(text("CRC 仅检测传输损坏。解码得到的载荷仍未认证，不会直接改变设备授权或开锁。真实声学效果与设备物理特征需另行采样验收。", 14));
        audioPage.addView(text("认证密钥分发", 22));
        audioPage.addView(text("先通过可信渠道核对发行端公钥，再生成本次接收请求。将请求 WAV 发送到发行端，接收回复 WAV 并解码后验证。会话最长 180 秒，仅保留在内存。", 16));
        issuer = field("发行端 ID（例如 laptop）", false);
        recipient = field("本机 ID（例如 iqoo）", false);
        issuerPin = field("已核对的发行端公钥 · SPKI Base64", true);
        audioPage.addView(issuer); audioPage.addView(recipient); audioPage.addView(issuerPin);
        audioPage.addView(button("导入发行端公钥 DER", () -> pick(PICK_ISSUER)));
        pinFingerprint = text("尚未选择发行端公钥", 14);
        audioPage.addView(pinFingerprint);
        pinVerified = new CheckBox(this);
        pinVerified.setText("我已通过可信渠道核对上述公钥指纹");
        audioPage.addView(pinVerified);
        issuerPin.addTextChangedListener(new android.text.TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                pinVerified.setChecked(false);
                try {
                    byte[] key = Base64.getDecoder().decode(s.toString().trim());
                    if (key.length == 0 || key.length > 256) throw new IllegalArgumentException();
                    pinFingerprint.setText("发行端公钥 SHA-256：\n" + digest(key));
                } catch (Exception invalid) { pinFingerprint.setText("请输入或导入有效的发行端 SPKI 公钥"); }
            }
            @Override public void afterTextChanged(android.text.Editable s) { }
        });
        audioPage.addView(button("生成接收请求 WAV", this::beginExchange));
        audioPage.addView(button("导出本次接收公钥 DER", () -> export(recipientPublicDer, "application/octet-stream", "receiver-public.der")));
        audioPage.addView(button("验证已解码的密钥包", this::acceptKeyPacket));
        audioPage.addView(button("生成密钥确认 WAV", () -> work(() -> {
            preparePacket(crypto.confirmationJson());
            return "已生成密钥确认 WAV，请发送给发行端。";
        })));
        message = field("测试消息（最多 1024 字节）", true);
        audioPage.addView(message);
        audioPage.addView(button("加密消息并生成 WAV", () -> {
            final String plaintext = message.getText().toString();
            work(() -> {
                preparePacket(crypto.encryptMessage(plaintext));
                runOnUiThread(() -> message.setText(""));
                return "已生成 AES-GCM 加密消息 WAV。接收端仍需验证会话和重放状态。";
            });
        }));
        audioPage.addView(button("结束密钥会话", () -> work(() -> {
            crypto.clear(); payload = null; recipientPublicDer = null;
            return "密钥会话已结束，内存会话密钥已清除。";
        })));
        audioScroll = scroll(audioPage);
        content.addView(audioScroll);
    }

    private void pick(int request) {
        if (blocked()) return;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        startActivityForResult(intent, request);
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (result != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        if (!"content".equals(uri.getScheme())) { status("仅支持系统文件选择器返回的文件"); return; }
        if (request == SAVE_FILE) {
            final byte[] bytes = exportBytes; exportBytes = null;
            if (bytes == null) return;
            work(() -> {
                try (OutputStream output = getContentResolver().openOutputStream(uri, "wt")) {
                    if (output == null) throw new IllegalStateException("无法写入选择的位置");
                    output.write(bytes);
                }
                return "已保存 " + bytes.length + " 字节";
            });
        } else if (request == PICK_WAV || request == PICK_PAYLOAD || request == PICK_ISSUER) {
            work(() -> {
                byte[] bytes;
                try (InputStream input = getContentResolver().openInputStream(uri)) {
                    bytes = WaveFile.readBounded(input, request == PICK_WAV ? WaveFile.MAX_BYTES
                            : request == PICK_ISSUER ? 256 : OfdmCodec.MAX_PAYLOAD);
                }
                if (request == PICK_ISSUER) {
                    java.security.PublicKey key = java.security.KeyFactory.getInstance("EC")
                            .generatePublic(new java.security.spec.X509EncodedKeySpec(bytes));
                    if (!(key instanceof java.security.interfaces.ECPublicKey)) throw new IllegalArgumentException("需要 EC 发行端公钥");
                    final String pin = Base64.getEncoder().encodeToString(bytes);
                    runOnUiThread(() -> issuerPin.setText(pin));
                    return "已导入发行端公钥。请通过可信渠道核对页面显示的 SHA-256 指纹。";
                }
                if (request == PICK_WAV) {
                    double[] samples = WaveFile.decode(bytes);
                    wave = bytes; payload = null;
                    return String.format(Locale.ROOT, "已导入 %.2f 秒 WAV，可播放或解码", samples.length / 48000.0);
                }
                wave = WaveFile.encode(OfdmCodec.encode(bytes)); payload = null;
                return "已生成 OFDM WAV\n载荷 " + bytes.length + " 字节 · SHA-256 " + digest(bytes);
            });
        }
    }

    private void decode() {
        if (wave == null) { status("请先导入或录制 WAV"); return; }
        final byte[] input = wave;
        work(() -> {
            byte[] decoded = OfdmCodec.decode(WaveFile.decode(input));
            payload = decoded;
            return "解码成功（尚未认证）\n" + decoded.length + " 字节 · SHA-256 " + digest(decoded);
        });
    }

    private void beginExchange() {
        if (!pinVerified.isChecked()) { status("请先通过可信渠道核对发行端公钥指纹并勾选确认"); return; }
        final String sender = issuer.getText().toString().trim();
        final String receiver = recipient.getText().toString().trim();
        final String pin = issuerPin.getText().toString().trim();
        work(() -> {
            String request = crypto.beginRequest(sender, receiver, pin);
            recipientPublicDer = Base64.getDecoder().decode(crypto.recipientPublicKeyBase64());
            preparePacket(request);
            return "已生成 180 秒有效的接收请求 WAV\n发行端公钥 SHA-256：" + digest(Base64.getDecoder().decode(pin))
                    + "\n本次接收方公钥 SHA-256：" + digest(recipientPublicDer)
                    + "\n请将接收公钥 DER 带外交给发行端并核对指纹。"
                    + "\n发送请求后，导入或录制回复 WAV → 解码 → 验证密钥包。";
        });
    }

    private void acceptKeyPacket() {
        if (payload == null) { status("先解码发行端回复 WAV"); return; }
        final byte[] received = payload.clone();
        work(() -> {
            String packet = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(received)).toString();
            crypto.acceptPacket(packet);
            return "发行端签名、请求绑定及有效期验证通过，已接收会话密钥。\n请生成密钥确认 WAV；此操作不产生开锁授权。";
        });
    }

    private void preparePacket(String packet) {
        byte[] bytes = packet.getBytes(StandardCharsets.UTF_8);
        wave = WaveFile.encode(OfdmCodec.encode(bytes));
        payload = bytes;
    }

    private void export(byte[] bytes, String type, String name) {
        if (blocked()) return;
        if (bytes == null) { status("没有可保存的数据"); return; }
        exportBytes = bytes.clone();
        startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                .setType(type).putExtra(Intent.EXTRA_TITLE, name), SAVE_FILE);
    }

    private void share(byte[] bytes, String name, String type) {
        if (blocked()) return;
        if (bytes == null) { status("没有可分享的数据"); return; }
        try {
            try (FileOutputStream output = new FileOutputStream(new File(getCacheDir(), "share-" + name))) {
                output.write(bytes);
            }
            Uri uri = Uri.parse("content://org.smartlock.course.exports/" + name);
            Intent intent = new Intent(Intent.ACTION_SEND).setType(type).putExtra(Intent.EXTRA_STREAM, uri)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            intent.setClipData(android.content.ClipData.newRawUri("音频实验导出", uri));
            startActivity(Intent.createChooser(intent, "选择分享位置"));
        } catch (Exception error) { status("分享失败：" + error.getMessage()); }
    }

    private void play() {
        if (blocked()) return;
        if (wave == null) { status("请先选择或生成 WAV"); return; }
        stopAudio();
        try {
            File file = new File(getCacheDir(), "playback.wav");
            try (FileOutputStream output = new FileOutputStream(file)) { output.write(wave); }
            MediaPlayer current = new MediaPlayer();
            player = current;
            current.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build());
            current.setDataSource(file.getAbsolutePath());
            current.setOnPreparedListener(prepared -> { if (player == prepared) { prepared.start(); status("正在播放 WAV，请保持适当音量"); } });
            current.setOnCompletionListener(completed -> { stopPlayer(); status("播放结束"); });
            current.setOnErrorListener((failed, what, extra) -> { stopPlayer(); status("音频播放失败"); return true; });
            current.prepareAsync();
        } catch (Exception error) { stopPlayer(); status("无法播放：" + error.getMessage()); }
    }

    private void requestRecording() {
        if (blocked()) return;
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            new AlertDialog.Builder(this).setTitle("使用麦克风进行音频实验")
                    .setMessage("仅在点击录音后采集，最多 10 秒。录音留在本机，只有你选择保存时才导出。")
                    .setNegativeButton("取消", null).setPositiveButton("继续", (d,w) ->
                        requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, MIC_PERMISSION)).show();
        } else startRecording();
    }

    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(request, permissions, grants);
        if (request == MIC_PERMISSION) {
            if (grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED)
                status("麦克风已授权。点击录音即可开始采集。");
            else status("未授予麦克风权限；仍可导入 WAV 进行实验");
        }
    }

    private void startRecording() {
        if (blocked()) return;
        stopPlayer();
        try {
            recorder.start(this, new PcmRecorder.Listener() {
                @Override public void finished(double[] samples, String source) {
                    byte[] recorded = WaveFile.encode(samples);
                    runOnUiThread(() -> {
                        if (destroyed) return;
                        wave = recorded; payload = null;
                        status(String.format(Locale.ROOT, "录音完成：%.2f 秒\n%s\n可解码或保存 WAV", samples.length / 48000.0, source));
                    });
                }
                @Override public void failed(String message) { runOnUiThread(() -> status("录音失败：" + message)); }
            });
            status("正在录音，10 秒后自动停止；也可点击停止");
        } catch (RuntimeException error) { status("无法录音：" + error.getMessage()); }
    }

    private boolean blocked() {
        if (busy || recorder.isRunning()) { status("请等待当前处理完成，或先停止录音"); return true; }
        return false;
    }
    private interface Job { String run() throws Exception; }
    private void work(Job task) {
        if (blocked()) return;
        stopPlayer(); busy = true; status("正在处理…");
        worker.execute(() -> {
            String message;
            try { message = task.run(); }
            catch (Exception error) { message = "操作失败：" + error.getMessage(); }
            final String result = message;
            runOnUiThread(() -> { busy = false; status(result); });
        });
    }

    private void show(String selected) {
        if ("web".equals(selected) && web == null) selected = "connect";
        if (!"audio".equals(selected)) stopAudio();
        page = selected;
        audioScroll.setVisibility("audio".equals(selected) ? View.VISIBLE : View.GONE);
        connectScroll.setVisibility("connect".equals(selected) ? View.VISIBLE : View.GONE);
        if (web != null) web.setVisibility("web".equals(selected) ? View.VISIBLE : View.GONE);
    }
    private void stopPlayer() { if (player != null) { player.release(); player = null; } }
    private void stopAudio() { stopPlayer(); recorder.stop(); }
    private void status(String message) { if (!destroyed) audioStatus.setText(message); }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private LinearLayout column() { LinearLayout result = new LinearLayout(this); result.setOrientation(LinearLayout.VERTICAL); return result; }
    private LinearLayout paddedColumn() { LinearLayout result = column(); result.setPadding(dp(20), dp(20), dp(20), dp(30)); return result; }
    private ScrollView scroll(View child) { ScrollView result = new ScrollView(this); result.setFillViewport(true); result.addView(child); return result; }
    private TextView text(String value, int size) { TextView result = new TextView(this); result.setText(value); result.setTextSize(size); result.setTextColor(Color.rgb(48, 40, 34)); result.setPadding(0, dp(6), 0, dp(6)); return result; }
    private Button button(String label, Runnable click) { Button result = new Button(this); result.setText(label); result.setAllCaps(false); result.setMinHeight(dp(48)); result.setOnClickListener(view -> click.run()); return result; }
    private EditText field(String hint, boolean multiline) {
        EditText value = new EditText(this); value.setHint(hint); value.setSingleLine(!multiline);
        value.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        value.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
                | (multiline ? android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE : 0));
        value.setFilters(new android.text.InputFilter[] {new android.text.InputFilter.LengthFilter(multiline ? 4096 : 50)});
        return value;
    }
    private static String digest(byte[] bytes) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder result = new StringBuilder();
        for (byte value : hash) result.append(String.format(Locale.ROOT, "%02x", value & 255));
        return result.toString();
    }
    @Override public void onConfigurationChanged(android.content.res.Configuration configuration) {
        super.onConfigurationChanged(configuration);
        // Resizing keeps the active experiment and WebView in memory; no keys enter saved state.
        content.requestLayout();
        if (web != null) web.invalidate();
    }
    @Override protected void onStop() { stopAudio(); if (web != null) web.onPause(); super.onStop(); }
    @Override protected void onResume() { super.onResume(); if (web != null) web.onResume(); }
    @Override protected void onDestroy() {
        destroyed = true; stopAudio(); worker.shutdownNow(); clearWeb(); crypto.clear();
        wave = null; payload = null; exportBytes = null; recipientPublicDer = null; super.onDestroy();
    }
    @Override public void onBackPressed() {
        navigateBack();
    }
    private void navigateBack() {
        if ("web".equals(page) && web != null && web.canGoBack()) web.goBack();
        else if (!"connect".equals(page)) show("connect");
        else finish();
    }
}
