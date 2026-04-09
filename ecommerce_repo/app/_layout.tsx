import React, { useEffect } from 'react';
import { Slot } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Platform, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

export default function RootLayout() {
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') {
      return;
    }

    const existing = document.querySelector(
      'link[data-font="roboto"]'
    ) as HTMLLinkElement | null;

    if (!existing) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href =
        'https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700;900&display=swap';
      link.setAttribute('data-font', 'roboto');
      document.head.appendChild(link);
    }

    document.body.style.fontFamily =
      "Roboto, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <View style={{ flex: 1, backgroundColor: '#EEF2FF' }}>
        <StatusBar style="dark" />
        <Slot />
      </View>
    </GestureHandlerRootView>
  );
}
