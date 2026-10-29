/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f3f7f5",
          100: "#e4efe9",
          200: "#c5ddd0",
          300: "#9bc3b0",
          400: "#6ba38b",
          500: "#4a8670",
          600: "#2d6a4f",
          700: "#1b4332",
          800: "#163828",
          900: "#122f22",
        },
      },
      fontFamily: {
        display: ['"Fraunces"', "Georgia", "serif"],
        sans: ['"Source Sans 3"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
