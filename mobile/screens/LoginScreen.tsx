import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator } from "react-native";
import { api, APIError } from "@/lib/api";
import { colors } from "@/lib/theme";

export default function LoginScreen({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleLogin() {
    setError(null);
    setSubmitting(true);
    try {
      await api.login(email.trim(), password);
      onLoggedIn();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Nova</Text>
      <Text style={styles.subtitle}>Sign in to your assistant</Text>

      {error && <Text style={styles.error}>{error}</Text>}

      <TextInput
        style={styles.input}
        placeholder="Email"
        placeholderTextColor={colors.muted}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        keyboardType="email-address"
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        placeholderTextColor={colors.muted}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
      />

      <TouchableOpacity style={styles.button} onPress={handleLogin} disabled={submitting}>
        {submitting ? <ActivityIndicator color={colors.base} /> : <Text style={styles.buttonText}>Sign in</Text>}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base, justifyContent: "center", padding: 24 },
  title: { color: colors.ink, fontSize: 32, fontWeight: "700", textAlign: "center", marginBottom: 4 },
  subtitle: { color: colors.muted, fontSize: 14, textAlign: "center", marginBottom: 24 },
  input: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    color: colors.ink,
    padding: 12,
    marginBottom: 12,
    fontSize: 15,
  },
  button: {
    backgroundColor: colors.accent,
    borderRadius: 8,
    padding: 14,
    alignItems: "center",
    marginTop: 8,
  },
  buttonText: { color: colors.base, fontWeight: "700", fontSize: 15 },
  error: {
    color: colors.danger,
    backgroundColor: "rgba(242,84,91,0.1)",
    borderWidth: 1,
    borderColor: "rgba(242,84,91,0.4)",
    borderRadius: 8,
    padding: 10,
    marginBottom: 12,
    fontSize: 13,
  },
});
