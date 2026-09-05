import React, { useState, useRef } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Modal,
} from "react-native";
import { api, APIError, ToolCall } from "@/lib/api";
import { colors } from "@/lib/theme";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export default function AssistantScreen() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<ToolCall | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  async function send() {
    const text = input.trim();
    if (!text) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setBusy(true);

    try {
      const reply = await api.chat(text);
      setMessages((prev) => [...prev, { role: "assistant", text: reply.reply }]);

      const needsConfirm = reply.tool_calls.find((tc) => tc.result === "REQUIRES_CONFIRMATION");
      if (needsConfirm) setPendingConfirm(needsConfirm);
    } catch (err) {
      const msg = err instanceof APIError ? err.message : "Something went wrong.";
      setMessages((prev) => [...prev, { role: "assistant", text: `⚠️ ${msg}` }]);
    } finally {
      setBusy(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }

  async function confirm(approved: boolean) {
    if (!pendingConfirm?.pending_id || !approved) {
      if (!approved) setMessages((prev) => [...prev, { role: "assistant", text: "Okay, I won't do that." }]);
      setPendingConfirm(null);
      return;
    }
    setPendingConfirm(null);
    setBusy(true);
    try {
      const result = await api.confirmPending(pendingConfirm.pending_id);
      setMessages((prev) => [...prev, { role: "assistant", text: result.message || `${result.tool_name}: ${result.result}` }]);
    } catch (err) {
      const msg = err instanceof APIError ? err.message : "Confirmation failed.";
      setMessages((prev) => [...prev, { role: "assistant", text: `⚠️ ${msg}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={90}
    >
      <Text style={styles.header}>Assistant</Text>

      <ScrollView ref={scrollRef} style={styles.messages} contentContainerStyle={{ paddingBottom: 12 }}>
        {messages.length === 0 && <Text style={styles.empty}>Ask Nova anything.</Text>}
        {messages.map((m, i) => (
          <View key={i} style={[styles.bubble, m.role === "user" ? styles.bubbleUser : styles.bubbleAssistant]}>
            <Text style={m.role === "user" ? styles.bubbleTextUser : styles.bubbleTextAssistant}>{m.text}</Text>
          </View>
        ))}
      </ScrollView>

      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          placeholder="Ask Nova anything…"
          placeholderTextColor={colors.muted}
          value={input}
          onChangeText={setInput}
          onSubmitEditing={send}
          editable={!busy}
        />
        <TouchableOpacity style={styles.sendButton} onPress={send} disabled={busy}>
          <Text style={styles.sendButtonText}>Send</Text>
        </TouchableOpacity>
      </View>

      <Modal visible={!!pendingConfirm} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Confirmation needed</Text>
            <Text style={styles.modalText}>
              {pendingConfirm?.message || `Run ${pendingConfirm?.tool_name}?`}
            </Text>
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalConfirm} onPress={() => confirm(true)}>
                <Text style={styles.modalConfirmText}>Confirm</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalCancel} onPress={() => confirm(false)}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base, padding: 16, paddingTop: 56 },
  header: { color: colors.ink, fontSize: 24, fontWeight: "700", marginBottom: 12 },
  messages: { flex: 1 },
  empty: { color: colors.muted, textAlign: "center", marginTop: 24 },
  bubble: { maxWidth: "85%", padding: 10, borderRadius: 10, marginBottom: 8 },
  bubbleUser: { backgroundColor: colors.accent, alignSelf: "flex-end" },
  bubbleAssistant: { backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border, alignSelf: "flex-start" },
  bubbleTextUser: { color: colors.base, fontSize: 14 },
  bubbleTextAssistant: { color: colors.ink, fontSize: 14 },
  inputRow: { flexDirection: "row", gap: 8 },
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
  sendButton: { backgroundColor: colors.accent, borderRadius: 8, paddingHorizontal: 16, justifyContent: "center" },
  sendButtonText: { color: colors.base, fontWeight: "700" },
  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "center", padding: 24 },
  modalCard: { backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.pending, borderRadius: 10, padding: 16 },
  modalTitle: { color: colors.pending, fontWeight: "700", fontSize: 15, marginBottom: 6 },
  modalText: { color: colors.ink, fontSize: 14, marginBottom: 16 },
  modalActions: { flexDirection: "row", gap: 8 },
  modalConfirm: { backgroundColor: colors.accent, borderRadius: 8, paddingVertical: 10, paddingHorizontal: 16 },
  modalConfirmText: { color: colors.base, fontWeight: "700" },
  modalCancel: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingVertical: 10, paddingHorizontal: 16 },
  modalCancelText: { color: colors.ink },
});
