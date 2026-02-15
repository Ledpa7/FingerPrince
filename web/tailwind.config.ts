import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          sky: "#8ed9ff",
          lemon: "#fde875",
          ink: "#14233c",
          slate: "#2f4063",
          paper: "#f6fbff",
        },
      },
      boxShadow: {
        bubble: "0 10px 28px rgba(20, 35, 60, 0.12)",
      },
      keyframes: {
        floatIn: {
          "0%": { opacity: "0", transform: "translateY(10px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
      },
      animation: {
        floatIn: "floatIn 240ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
