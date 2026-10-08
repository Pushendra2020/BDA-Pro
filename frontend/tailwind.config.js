/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Arial", "Helvetica Neue", "sans-serif"],
        display: ["Georgia", "Times New Roman", "serif"],
        mono: ["Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
