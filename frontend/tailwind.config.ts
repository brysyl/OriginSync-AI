import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#080d13",
        panel: "#101923",
        line: "#24313d",
        mint: "#43d9a3",
      },
    },
  },
  plugins: [],
};

export default config;
