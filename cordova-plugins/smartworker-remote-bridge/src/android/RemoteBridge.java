package com.smartworker.bridge;

import org.apache.cordova.CordovaPlugin;

/**
 * Allows the native bridge for the deployed site, and only for it.
 *
 * Cordova's default lets only the launch page (https://localhost/...) talk
 * to native code. Returning null for every other URL keeps that default, so
 * nothing else the WebView might show gains access.
 */
public class RemoteBridge extends CordovaPlugin {

    private String allowedPrefix() {
        String origin = preferences.getString("RemoteBridgeOrigin", "");
        if (origin == null || origin.isEmpty()) {
            return null;
        }
        // "https://example.com" must not also match "https://example.com.evil.net".
        return origin.endsWith("/") ? origin : origin + "/";
    }

    @Override
    public Boolean shouldAllowBridgeAccess(String url) {
        String prefix = allowedPrefix();
        if (prefix != null && url != null && url.startsWith(prefix)) {
            return true;
        }
        return null;
    }
}
