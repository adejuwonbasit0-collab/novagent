import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0B0E14",
        panel: "#10141D",
        border: "#1C2130",
        ink: "#E7E9EE",
        muted: "#8B92A6",
        accent: {
          DEFAULT: "#7C8CFF",
          dim: "#5A67D8",
        },
        active: "#2DD4BF",
        pending: "#F5A623",
        danger: "#F2545B",
      },
      fontFamily: {
        display: ["var(--font-space-grotesk)", "sans-serif"],
        body: ["var(--font-inter)", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      },
      borderRadius: {
        DEFAULT: "6px",
      },
    },
  },
  plugins: [],
};

export default config;
