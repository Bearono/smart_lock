package org.smartlock.course;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.http.SslError;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.ByteArrayInputStream;

/** Mobile shell for the same authenticated door workflow as the web client. */
public final class MainActivity extends Activity {
    private static final int BLUE = 0xff005ecb, INK = 0xff1c1c1e, MUTED = 0xff595963;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private FrameLayout content;
    private ScrollView connectionPage, errorPage;
    private TextView connectionStatus, errorTitle, errorDetail;
    private EditText endpoint;
    private Button returnButton, connectButton;
    private ProgressBar progress;
    private WebView web;
    private OriginPolicy policy;
    private boolean settingsVisible = true, loadFailed, destroyed, clearing;
    private final Runnable loadTimeout = () -> fail("连接超时", "请检查网络和服务是否运行，然后重试。");

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        LinearLayout root = column();
        root.setBackgroundColor(0xfff5f6f8);
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets edges = insets.getInsets(
                        android.view.WindowInsets.Type.systemBars() | android.view.WindowInsets.Type.ime());
                view.setPadding(edges.left, edges.top, edges.right, edges.bottom);
                return insets;
            });
        } else root.setFitsSystemWindows(true);
        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(18), dp(4), dp(12), dp(4));
        toolbar.setBackgroundColor(Color.WHITE);
        LinearLayout brand = column();
        TextView title = text("安居 · SmartLock", 17, INK);
        title.setTypeface(null, Typeface.BOLD);
        brand.addView(title);
        connectionStatus = text("连接你的家", 12, MUTED);
        connectionStatus.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        brand.addView(connectionStatus);
        toolbar.addView(brand, new LinearLayout.LayoutParams(0, -2, 1));
        toolbar.addView(button("连接设置", false, () -> showSettings(true)),
                new LinearLayout.LayoutParams(-2, dp(48)));
        root.addView(toolbar);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setProgressTintList(ColorStateList.valueOf(BLUE));
        progress.setVisibility(View.INVISIBLE);
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));
        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        buildConnectionPage();
        buildErrorPage();
        setContentView(root);
        if (android.os.Build.VERSION.SDK_INT >= 33)
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::navigateBack);
        String saved = getPreferences(MODE_PRIVATE).getString("endpoint", getString(R.string.default_service_url));
        endpoint.setText(saved);
        if (!saved.isEmpty()) connect(); else showSettings(true);
    }

    private void buildConnectionPage() {
        LinearLayout body = paddedColumn();
        body.addView(text("⌂", 48, BLUE));
        TextView title = text("连接我的家", 28, INK);
        title.setTypeface(null, Typeface.BOLD);
        body.addView(title);
        LinearLayout card = paddedColumn();
        card.setBackground(rounded(Color.WHITE, 24));
        LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(-1, -2);
        cardParams.topMargin = dp(28);
        body.addView(card, cardParams);
        card.addView(text("服务地址", 16, INK));
        endpoint = new EditText(this);
        endpoint.setContentDescription("门锁服务 HTTPS 地址");
        endpoint.setHint("https://lock.example.com:8443");
        endpoint.setSingleLine(true);
        endpoint.setTextSize(16);
        endpoint.setTextColor(INK);
        endpoint.setHintTextColor(MUTED);
        endpoint.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        endpoint.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        endpoint.setFilters(new android.text.InputFilter[] {new android.text.InputFilter.LengthFilter(512)});
        card.addView(endpoint, new LinearLayout.LayoutParams(-1, dp(60)));
        card.addView(text("填写部署时提供的 HTTPS 地址，并保持手机与服务网络连通。", 14, MUTED));
        connectButton = button("连接我的家", true, this::connect);
        addAction(card, connectButton);
        returnButton = button("返回门锁", false, () -> {
            if (web == null) retry(); else showSettings(false);
        });
        addAction(card, returnButton);
        addAction(body, button("清除本机登录状态", false, this::confirmClearSession));
        body.addView(text("SmartLock 1.1 · 智能门锁", 12, MUTED));
        connectionPage = scroll(body);
        content.addView(connectionPage);
    }

    private void buildErrorPage() {
        LinearLayout body = paddedColumn();
        body.setGravity(Gravity.CENTER_VERTICAL);
        errorTitle = text("暂时无法连接", 26, INK);
        errorTitle.setTypeface(null, Typeface.BOLD);
        errorDetail = text("", 16, MUTED);
        errorDetail.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        body.addView(errorTitle);
        body.addView(errorDetail);
        addAction(body, button("重新连接", true, this::retry));
        addAction(body, button("检查连接设置", false, () -> showSettings(true)));
        errorPage = scroll(body);
        errorPage.setBackgroundColor(0xfff5f6f8);
        errorPage.setVisibility(View.GONE);
        content.addView(errorPage);
    }

    private void connect() {
        if (clearing) return;
        final OriginPolicy selected;
        try { selected = new OriginPolicy(endpoint.getText().toString()); }
        catch (IllegalArgumentException invalid) { endpoint.setError(invalid.getMessage()); return; }
        ((InputMethodManager) getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(endpoint.getWindowToken(), 0);
        String previous = getPreferences(MODE_PRIVATE).getString("endpoint", "");
        if (web != null && policy != null && policy.origin().equals(selected.origin())) {
            if (loadFailed) retry(); else showSettings(false);
            return;
        }
        destroyWeb();
        policy = selected;
        Runnable open = () -> {
            if (destroyed) return;
            getPreferences(MODE_PRIVATE).edit().putString("endpoint", selected.origin()).apply();
            endpoint.setText(selected.origin());
            createWeb();
            retry();
        };
        if (!previous.isEmpty() && !previous.equals(selected.origin())) clearSession(open);
        else open.run();
    }

    @SuppressLint("SetJavaScriptEnabled") // Same-origin Vue UI; no native JavaScript bridge.
    private void createWeb() {
        final OriginPolicy selected = policy;
        WebView created = new WebView(this);
        web = created;
        WebSettings settings = created.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true); // Appearance preferences only; authentication uses HttpOnly cookies.
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
        created.setBackgroundColor(0xfff5f6f8);
        created.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(created, false);
        created.setWebChromeClient(new WebChromeClient() {
            @Override public void onPermissionRequest(PermissionRequest request) { request.deny(); }
            @Override public void onProgressChanged(WebView view, int value) {
                if (web == view && !loadFailed) progress.setProgress(value);
            }
        });
        created.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                if (view != web) return;
                if (!selected.allows(url)) { fail("地址已拦截", "请使用已配置的门锁服务。"); return; }
                beginLoading();
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                boolean allowed = selected.allows(request.getUrl().toString());
                if (!allowed) connectionStatus.setText("已拦截外部地址");
                return !allowed;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (selected.allows(url)) return null;
                byte[] png = OriginPolicy.inlinePng(url);
                return png == null ? new WebResourceResponse("text/plain", "UTF-8", new ByteArrayInputStream(new byte[0]))
                        : new WebResourceResponse("image/png", null, new ByteArrayInputStream(png));
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handle, SslError error) {
                handle.cancel();
                if (view == web) fail("无法验证服务身份", "请核对服务地址、手机时间和部署证书，再重新连接。");
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (view == web && request.isForMainFrame()) fail("暂时无法连接", "请确认网络畅通、门锁服务已启动，然后重试。");
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (view == web && request.isForMainFrame()) fail("服务暂不可用", "服务返回 " + response.getStatusCode() + "，请稍后重试。");
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (view != web || loadFailed || !selected.allows(url)) return;
                handler.removeCallbacks(loadTimeout);
                progress.setVisibility(View.INVISIBLE);
                connectionStatus.setText("已连接");
                CookieManager.getInstance().flush();
            }
            @Override public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                if (view == web) {
                    destroyWeb();
                    fail("页面需要重新加载", "页面进程已结束，重新连接即可继续。请先确认最近操作的执行结果。");
                }
                return true;
            }
        });
        content.addView(created, 0, new FrameLayout.LayoutParams(-1, -1));
    }

    private void beginLoading() {
        handler.removeCallbacks(loadTimeout);
        loadFailed = false;
        errorPage.setVisibility(View.GONE);
        connectionStatus.setText("正在连接…");
        progress.setProgress(0);
        progress.setVisibility(View.VISIBLE);
        handler.postDelayed(loadTimeout, 20000);
    }

    private void retry() {
        if (clearing) return;
        if (policy == null) { showSettings(true); return; }
        if (web == null) createWeb();
        beginLoading();
        showSettings(false);
        // Always load the home GET. Never resubmit a POST or repeat a door command.
        web.loadUrl(policy.origin() + "/");
    }

    private void fail(String title, String detail) {
        if (destroyed) return;
        handler.removeCallbacks(loadTimeout);
        loadFailed = true;
        if (web != null) web.stopLoading();
        progress.setVisibility(View.INVISIBLE);
        connectionStatus.setText("连接需要检查");
        errorTitle.setText(title);
        errorDetail.setText(detail);
        errorPage.setVisibility(settingsVisible ? View.GONE : View.VISIBLE);
    }

    private void showSettings(boolean visible) {
        settingsVisible = visible;
        connectionPage.setVisibility(visible ? View.VISIBLE : View.GONE);
        returnButton.setVisibility(policy != null ? View.VISIBLE : View.GONE);
        errorPage.setVisibility(!visible && loadFailed ? View.VISIBLE : View.GONE);
        if (web != null) web.setVisibility(visible ? View.GONE : View.VISIBLE);
    }

    private void confirmClearSession() {
        new AlertDialog.Builder(this).setTitle("清除本机登录状态？")
                .setMessage("清除后需要重新登录。只影响这部手机；账号退出请使用门锁页面里的退出登录。")
                .setNegativeButton("取消", null).setPositiveButton("清除", (dialog, which) -> {
                    destroyWeb();
                    clearSession(() -> { connectionStatus.setText("已清除，请重新连接"); showSettings(true); });
                }).show();
    }

    private void clearSession(Runnable complete) {
        clearing = true;
        connectButton.setEnabled(false);
        WebStorage.getInstance().deleteAllData();
        CookieManager.getInstance().removeAllCookies(removed -> {
            clearing = false;
            if (!destroyed) { connectButton.setEnabled(true); complete.run(); }
        });
    }

    private void destroyWeb() {
        handler.removeCallbacks(loadTimeout);
        progress.setVisibility(View.INVISIBLE);
        if (web == null) return;
        WebView old = web;
        web = null;
        content.removeView(old);
        old.destroy();
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private LinearLayout column() { LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.VERTICAL); return view; }
    private LinearLayout paddedColumn() { LinearLayout view = column(); view.setPadding(dp(24), dp(24), dp(24), dp(24)); return view; }
    private ScrollView scroll(View child) { ScrollView view = new ScrollView(this); view.setFillViewport(true); view.addView(child); return view; }
    private TextView text(String label, int size, int color) {
        TextView view = new TextView(this); view.setText(label); view.setTextSize(size); view.setTextColor(color);
        view.setPadding(0, dp(4), 0, dp(4)); return view;
    }
    private GradientDrawable rounded(int color, int radius) {
        GradientDrawable drawable = new GradientDrawable(); drawable.setColor(color); drawable.setCornerRadius(dp(radius)); return drawable;
    }
    private Button button(String label, boolean primary, Runnable action) {
        Button view = new Button(this); view.setText(label); view.setTextSize(15); view.setAllCaps(false);
        view.setMinHeight(dp(48)); view.setPadding(dp(16), dp(8), dp(16), dp(8));
        view.setTextColor(primary ? Color.WHITE : BLUE);
        view.setBackground(new android.graphics.drawable.RippleDrawable(ColorStateList.valueOf(0x22005ecb),
                rounded(primary ? BLUE : 0xffeaf2ff, 16), null));
        view.setOnClickListener(v -> action.run()); return view;
    }
    private void addAction(LinearLayout parent, Button button) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.topMargin = dp(14); parent.addView(button, params);
    }
    @Override public void onConfigurationChanged(android.content.res.Configuration config) {
        super.onConfigurationChanged(config); content.requestLayout(); if (web != null) web.invalidate();
    }
    @Override protected void onStop() { if (web != null) web.onPause(); CookieManager.getInstance().flush(); super.onStop(); }
    @Override protected void onResume() { super.onResume(); if (web != null) web.onResume(); }
    @Override protected void onDestroy() { destroyed = true; destroyWeb(); super.onDestroy(); }
    @Override public void onBackPressed() { navigateBack(); }
    private void navigateBack() {
        if (settingsVisible && policy != null) { showSettings(false); if (web == null) retry(); }
        else if (!settingsVisible && !loadFailed && web != null && web.canGoBack()) web.goBack();
        else moveTaskToBack(true);
    }
}
