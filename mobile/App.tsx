import React, { useEffect, useState, useCallback } from "react";
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from "react-native";
import { StatusBar } from "expo-status-bar";
import { api, isLoggedIn } from "@/lib/api";
import { colors } from "@/lib/theme";
import LoginScreen from "@/screens/LoginScreen";
import RemindersScreen from "@/screens/RemindersScreen";
import AssistantScreen from "@/screens/AssistantScreen";

type Tab = "reminders" | "assistant";

export default function App() {
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [loggedIn, setLoggedIn] = useState(false);
  const [tab, setTab] = useState<Tab>("assistant");

  const checkAuth = useCallback(async () => {
    const has = await isLoggedIn();
    if (has) {
      // A stored token isn't proof it's still valid — confirm against the
      // backend rather than trusting local storage alone (mirrors the
      // dashboard's own /auth/me check on load).
      try {
        await api.me();
        setLoggedIn(true);
      } catch {
        await api.logout();
        setLoggedIn(false);
      }
    } else {
      setLoggedIn(false);
    }
    setCheckingAuth(false);
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  if (checkingAuth) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  if (!loggedIn) {
    return (
      <>
        <StatusBar style="light" />
        <LoginScreen onLoggedIn={() => setLoggedIn(true)} />
      </>
    );
  }

  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <View style={styles.screen}>
        {tab === "reminders" ? <RemindersScreen /> : <AssistantScreen />}
      </View>

      <View style={styles.tabBar}>
        <TouchableOpacity style={styles.tabButton} onPress={() => setTab("assistant")}>
          <Text style={[styles.tabLabel, tab === "assistant" && styles.tabLabelActive]}>Assistant</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.tabButton} onPress={() => setTab("reminders")}>
          <Text style={[styles.tabLabel, tab === "reminders" && styles.tabLabelActive]}>Reminders</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.tabButton}
          onPress={async () => {
            await api.logout();
            setLoggedIn(false);
          }}
        >
          <Text style={styles.tabLabel}>Sign out</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, backgroundColor: colors.base, justifyContent: "center", alignItems: "center" },
  container: { flex: 1, backgroundColor: colors.base },
  screen: { flex: 1 },
  tabBar: {
    flexDirection: "row",
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.panel,
    paddingVertical: 10,
    paddingBottom: 24, // rough safe-area allowance without pulling in a dependency
  },
  tabButton: { flex: 1, alignItems: "center" },
  tabLabel: { color: colors.muted, fontSize: 12 },
  tabLabelActive: { color: colors.accent, fontWeight: "700" },
});
