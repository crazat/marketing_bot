/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // [Z1] 폰트 스택 확장 — Pretendard / Paperlogy / D2Coding
      fontFamily: {
        sans: [
          '"Pretendard Variable"',
          'Pretendard',
          '-apple-system',
          'BlinkMacSystemFont',
          'system-ui',
          'Roboto',
          'sans-serif',
        ],
        // [RECOVER OS] 디스플레이 = Fraunces (KPI 숫자·h1·값), mono = IBM Plex Mono (라벨·eyebrow)
        display: ['Fraunces', '"Pretendard Variable"', 'serif'],
        mono: ['"IBM Plex Mono"', 'D2Coding', '"JetBrains Mono"', 'Menlo', 'Monaco', 'monospace'],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // [RECOVER OS] raw 토큰 매핑 — bg-surface / text-sage / border-hair / text-strong …
        surface: {
          DEFAULT: "var(--surface)",
          2: "var(--surface-2)",
          3: "var(--surface-3)",
          hover: "var(--surface-hover)",
        },
        ink: "var(--bg-grain)",
        hair: {
          DEFAULT: "var(--hair)",
          strong: "var(--hair-strong)",
          spine: "var(--hair-spine)",
        },
        strong: "var(--text-strong)",
        faint: "var(--text-faint)",
        sage: {
          DEFAULT: "var(--sage)",
          fill: "var(--sage-fill)",
          deep: "var(--sage-deep)",
          tint: "var(--sage-tint)",
        },
        clay: { DEFAULT: "var(--clay)", tint: "var(--clay-tint)" },
        mist: { DEFAULT: "var(--mist)", tint: "var(--mist-tint)" },
        ok: { DEFAULT: "var(--ok)", tint: "var(--ok-tint)" },
        warn: { DEFAULT: "var(--warn)", tint: "var(--warn-tint)" },
        danger: { DEFAULT: "var(--danger)", tint: "var(--danger-tint)" },
        info: { DEFAULT: "var(--info)", tint: "var(--info-tint)" },
        d1: "var(--d1)", d2: "var(--d2)", d3: "var(--d3)", d4: "var(--d4)",
        d5: "var(--d5)", d6: "var(--d6)", d7: "var(--d7)", d8: "var(--d8)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        pop: "var(--shadow-pop)",
        cta: "var(--shadow-cta)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        card: "var(--r-card)",
        inner: "var(--r-inner)",
        chip: "var(--r-chip)",
        pill: "var(--r-pill)",
      },
      keyframes: {
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '10%, 30%, 50%, 70%, 90%': { transform: 'translateX(-2px)' },
          '20%, 40%, 60%, 80%': { transform: 'translateX(2px)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-down': {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        shake: 'shake 0.5s ease-in-out',
        'fade-in': 'fade-in 0.2s ease-out',
        'slide-up': 'slide-up 0.3s ease-out',
        'slide-down': 'slide-down 0.3s ease-out',
      },
    },
  },
  plugins: [],
}
