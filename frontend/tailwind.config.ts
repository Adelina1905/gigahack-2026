import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Backgrounds
        background: {
          DEFAULT: "#FFFFFF", // Primary background
          secondary: "#F5F5F5", // Secondary background
        },
        // Brand blues
        primary: {
          50: "#E6F0F9",
          100: "#CCE1F3",
          200: "#99C3E7",
          300: "#66A5DB",
          400: "#3387CF",
          500: "#00549C", // Primary blue
          600: "#004784",
          700: "#003A8D", // Dark blue
          800: "#002C69",
          900: "#001E47",
          DEFAULT: "#00549C",
          dark: "#003A8D",
        },
        // Text
        text: {
          DEFAULT: "#000000", // Primary text
          muted: "#4D4D4D",
          subtle: "#7A7A7A",
          inverted: "#FFFFFF",
        },
        // Accent / warning
        accent: {
          DEFAULT: "#FFBF00",
          light: "#FFD54D",
          dark: "#CC9900",
        },
        // Supporting semantic colors (complementary to the palette)
        success: {
          DEFAULT: "#1E8A5F",
          light: "#E3F5EC",
        },
        danger: {
          DEFAULT: "#D6403A",
          light: "#FBE7E6",
        },
        info: {
          DEFAULT: "#00549C",
          light: "#E6F0F9",
        },
        border: {
          DEFAULT: "#E0E0E0",
          strong: "#BFBFBF",
        },
      },
      fontFamily: {
        // Main display font
        sans: ["Railway", "Raleway", "sans-serif"],
        railway: ["Railway", "Raleway", "sans-serif"],
        // Secondary, most-used body font
        inter: ["Inter", "sans-serif"],
      },
      fontWeight: {
        light: "300",
        normal: "400",
        medium: "500",
        semibold: "600",
        bold: "700",
        extrabold: "800",
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1rem" }],       // 12px
        sm: ["0.875rem", { lineHeight: "1.25rem" }],    // 14px
        base: ["1rem", { lineHeight: "1.5rem" }],       // 16px
        md: ["1.125rem", { lineHeight: "1.75rem" }],    // 18px
        lg: ["1.25rem", { lineHeight: "1.875rem" }],    // 20px
        xl: ["1.5rem", { lineHeight: "2rem" }],         // 24px
        "2xl": ["1.875rem", { lineHeight: "2.25rem" }], // 30px
        "3xl": ["2.25rem", { lineHeight: "2.5rem" }],   // 36px
        "4xl": ["3rem", { lineHeight: "1.1" }],         // 48px
        "5xl": ["3.75rem", { lineHeight: "1.1" }],      // 60px
      },
    },
  },
  plugins: [],
};

export default config;