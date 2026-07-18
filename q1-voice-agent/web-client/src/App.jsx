import { useCallback, useEffect, useState } from "react";
import { PipecatClient } from "@pipecat-ai/client-js";
import {
  ProtobufFrameSerializer,
  WebSocketTransport,
} from "@pipecat-ai/websocket-transport";
import { PipecatClientProvider, PipecatClientAudio } from "@pipecat-ai/client-react";

const WS_URL = window.location.hostname.includes("app.github.dev")
  ? `wss://${window.location.hostname.replace("-5173.", "-7860.")}/ws`
  : "ws://localhost:7860/ws";

function VoiceAgent() {
  const [status, setStatus] = useState("idle");
  const [transcript, setTranscript] = useState([]);
  const [micLevel, setMicLevel] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");

  const addMessage = (role, text) => {
    setTranscript((prev) => [...prev, { role, text, id: Date.now() + Math.random() }]);
  };

  const [client] = useState(() =>
    new PipecatClient({
      transport: new WebSocketTransport({
      serializer: new ProtobufFrameSerializer(),
      recorderSampleRate: 16000,
      playerSampleRate: 48000,
      }),
      enableMic: true,
      enableCam: false,
      mediaStreamConstraints: {
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      },
      callbacks: {
        onConnected: () => {
          setStatus("connected");
          addMessage("system", "Connected to Priya");
        },
        onDisconnected: () => {
          setStatus("idle");
          addMessage("system", "Call ended");
        },
        onTransportStateChanged: (state) => {
          console.log("Transport state:", state);
        },
        onBotReady: () => {
          addMessage("system", "Priya is ready");
        },
        onLocalAudioLevel: (level) => {
          setMicLevel(level);
        },
        onUserTranscript: (data) => {
          if (data.final) addMessage("user", data.text);
        },
        onBotTranscript: (data) => {
          addMessage("agent", data.text);
        },
        onError: (err) => {
          console.error("Error:", err);
          setErrorMessage(err?.message || "Voice connection failed");
          setStatus("error");
        },
      },
    })
  );

  const startCall = useCallback(async () => {
    setStatus("connecting");
    setTranscript([]);
    setErrorMessage("");
    setMicLevel(0);

    try {
      await client.connect({ wsUrl: WS_URL });
    } catch (err) {
      console.error("Connect failed:", err);
      setErrorMessage(err?.message || "Could not connect to Priya");
      setStatus("error");
    }
  }, [client]);

  const endCall = useCallback(async () => {
    await client.disconnect();
    setMicLevel(0);
    setStatus("idle");
  }, [client]);

  useEffect(() => {
    return () => {
      client.disconnect();
    };
  }, [client]);

  const statusColor = {
    idle: "#6b7280",
    connecting: "#f59e0b",
    connected: "#16a34a",
    error: "#dc2626",
  }[status] || "#6b7280";

  const statusLabel = {
    idle: "Ready to connect",
    connecting: "Connecting...",
    connected: "Connected - Priya is listening",
    error: "Connection error",
  }[status];

  return (
    <PipecatClientProvider client={client}>
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.logo}>STAR HEALTH INSURANCE</div>
          <div style={styles.avatar}>👩‍💼</div>
          <h1 style={styles.name}>Hi, I'm Priya</h1>
          <p style={styles.subtitle}>Your Health Insurance Renewal Specialist</p>

          <div style={{ ...styles.status, color: statusColor }}>
            {statusLabel}
          </div>

          {errorMessage && <div style={styles.error}>{errorMessage}</div>}

          {status === "connected" && (
            <div style={styles.micMeter} aria-label="Microphone level">
              <div
                style={{
                  ...styles.micMeterFill,
                  width: `${Math.min(100, Math.round(micLevel * 100))}%`,
                }}
              />
            </div>
          )}

          {status === "idle" || status === "error" ? (
            <button style={styles.btnStart} onClick={startCall}>
              📞 Start Voice Consultation
            </button>
          ) : (
            <button style={styles.btnEnd} onClick={endCall}>
              End Call
            </button>
          )}

          {transcript.length > 0 && (
            <div style={styles.transcript}>
              {transcript.map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    ...styles.msg,
                    color:
                      msg.role === "agent"
                        ? "#e63329"
                        : msg.role === "user"
                          ? "#374151"
                          : "#9ca3af",
                    fontStyle: msg.role === "system" ? "italic" : "normal",
                  }}
                >
                  {msg.role === "agent" && "🤖 Priya: "}
                  {msg.role === "user" && "👤 You: "}
                  {msg.text}
                </div>
              ))}
            </div>
          )}

          <PipecatClientAudio />
        </div>
      </div>
    </PipecatClientProvider>
  );
}

export default function App() {
  return <VoiceAgent />;
}

const styles = {
  container: {
    minHeight: "100vh",
    background: "#f0f4f8",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  card: {
    background: "white",
    borderRadius: 16,
    padding: 40,
    width: 380,
    boxShadow: "0 4px 24px rgba(0,0,0,0.1)",
    textAlign: "center",
  },
  logo: {
    fontSize: 12,
    color: "#e63329",
    fontWeight: 700,
    letterSpacing: 1,
    marginBottom: 8,
  },
  avatar: {
    width: 80,
    height: 80,
    background: "linear-gradient(135deg, #e63329, #ff6b6b)",
    borderRadius: "50%",
    margin: "0 auto 16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 32,
  },
  name: { fontSize: 22, color: "#1a1a2e", margin: "0 0 4px" },
  subtitle: { fontSize: 14, color: "#666", marginBottom: 24 },
  status: { fontSize: 13, marginBottom: 10, minHeight: 20 },
  error: {
    color: "#dc2626",
    fontSize: 12,
    marginBottom: 12,
    wordBreak: "break-word",
  },
  micMeter: {
    height: 8,
    background: "#e5e7eb",
    borderRadius: 999,
    marginBottom: 16,
    overflow: "hidden",
  },
  micMeterFill: {
    height: "100%",
    background: "#16a34a",
    transition: "width 80ms linear",
  },
  btnStart: {
    width: "100%",
    padding: 14,
    background: "#e63329",
    color: "white",
    border: "none",
    borderRadius: 10,
    fontSize: 16,
    fontWeight: 600,
    cursor: "pointer",
  },
  btnEnd: {
    width: "100%",
    padding: 14,
    background: "#f1f5f9",
    color: "#374151",
    border: "none",
    borderRadius: 10,
    fontSize: 16,
    fontWeight: 600,
    cursor: "pointer",
    marginTop: 8,
  },
  transcript: {
    marginTop: 24,
    textAlign: "left",
    maxHeight: 200,
    overflowY: "auto",
    border: "1px solid #e5e7eb",
    borderRadius: 8,
    padding: 12,
  },
  msg: {
    fontSize: 13,
    marginBottom: 8,
    lineHeight: 1.4,
  },
};
