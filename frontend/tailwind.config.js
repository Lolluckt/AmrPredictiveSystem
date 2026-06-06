
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
      colors: {
        brand: {
          50: "#eef6ff",
          100: "#d9eaff",
          200: "#b6d5ff",
          300: "#85b7ff",
          400: "#4f8fff",
          500: "#2a6bf2",
          600: "#1c50d4",
          700: "#183fa8",
          800: "#163686",
          900: "#142e6c",
        },
      },
    },
  },
  plugins: [],
};
