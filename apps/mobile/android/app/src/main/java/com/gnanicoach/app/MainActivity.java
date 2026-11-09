package com.gnanicoach.app;

import android.os.Bundle;

import androidx.activity.EdgeToEdge;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // The Capacitor 8 SystemBars docs ask for this when insetsHandling is
        // not "disable", so the WebView is edge-to-edge and the CSS safe-area
        // variables are correct. Source:
        // https://capacitorjs.com/docs/apis/system-bars (checked 2026-11-09).
        EdgeToEdge.enable(this);
        super.onCreate(savedInstanceState);
    }
}
