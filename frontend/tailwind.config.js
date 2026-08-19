/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#12203A",
        slate: {
          950: "#0B1526",
        },
        brand: {
          50: "#EEF3FB",
          100: "#D9E4F5",
          200: "#B3C9EB",
          300: "#82A6DB",
          400: "#4E7FC7",
          500: "#2E5FA8",
          600: "#234A85",
          700: "#1C3B69",
          800: "#172F54",
          900: "#12203A",
        },
        accent: {
          500: "#C77D3A",
          600: "#AD6529",
        },
        ok: "#2E7D53",
        warn: "#B8862B",
        danger: "#B4432E",
      },
      fontFamily: {
        display: ["'Fraunces'", "serif"],
        sans: ["'Inter'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(18,32,58,0.06), 0 1px 12px rgba(18,32,58,0.04)",
      },
    },
  },
  plugins: [],
}
