import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  TextInput,
  ActivityIndicator,
} from "react-native";
import { api, Reminder, APIError } from "@/lib/api";
import { colors } from "@/lib/theme";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

export default function RemindersScreen() {
  const [reminders, setReminders] = useState<Reminder[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      setReminders(await api.listReminders());
      setError(null);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to load reminders.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onRefresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  async function handleAdd() {
    if (!title.trim()) return;
    setAdding(true);
    try {
      const dueAt = new Date(Date.now() + 60 * 60 * 1000).toISOString(); // default: 1hr from now
      await api.createReminder(title.trim(), dueAt);
      setTitle("");
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to add reminder.");
    } finally {
      setAdding(false);
    }
  }

  async function handleComplete(id: string) {
    try {
      await api.completeReminder(id);
      await load();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to update reminder.");
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.header}>Reminders</Text>

      {error && <Text style={styles.error}>{error}</Text>}

      <View style={styles.addRow}>
        <TextInput
          style={styles.input}
          placeholder="New reminder…"
          placeholderTextColor={colors.muted}
          value={title}
          onChangeText={setTitle}
          onSubmitEditing={handleAdd}
        />
        <TouchableOpacity style={styles.addButton} onPress={handleAdd} disabled={adding}>
          {adding ? <ActivityIndicator color={colors.base} size="small" /> : <Text style={styles.addButtonText}>Add</Text>}
        </TouchableOpacity>
      </View>

      {reminders === null ? (
        <ActivityIndicator color={colors.accent} style={{ marginTop: 24 }} />
      ) : (
        <FlatList
          data={reminders.filter((r) => r.status === "pending")}
          keyExtractor={(r) => r.id}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
          ListEmptyComponent={<Text style={styles.empty}>Nothing pending.</Text>}
          renderItem={({ item }) => (
            <View style={styles.card}>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>{item.title}</Text>
                <Text style={styles.cardMeta}>{formatDate(item.due_at)}</Text>
              </View>
              <TouchableOpacity style={styles.completeButton} onPress={() => handleComplete(item.id)}>
                <Text style={styles.completeButtonText}>Done</Text>
              </TouchableOpacity>
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base, padding: 16, paddingTop: 56 },
  header: { color: colors.ink, fontSize: 24, fontWeight: "700", marginBottom: 16 },
  addRow: { flexDirection: "row", gap: 8, marginBottom: 16 },
  input: {
    flex: 1,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    color: colors.ink,
    padding: 10,
    fontSize: 14,
  },
  addButton: { backgroundColor: colors.accent, borderRadius: 8, paddingHorizontal: 16, justifyContent: "center" },
  addButtonText: { color: colors.base, fontWeight: "700" },
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
    flexDirection: "row",
    alignItems: "center",
  },
  cardTitle: { color: colors.ink, fontSize: 15, fontWeight: "500" },
  cardMeta: { color: colors.muted, fontSize: 12, marginTop: 2 },
  completeButton: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  completeButtonText: { color: colors.ink, fontSize: 12 },
  empty: { color: colors.muted, textAlign: "center", marginTop: 24 },
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
