export const theme = {
  colors: {
    // Brand
    purple: "#7132f5",
    purpleDark: "#5741d8",
    purpleDeep: "#5b1ecf",
    purpleSubtle: "rgba(133,91,251,0.16)",
    purpleBg: "rgba(133,91,251,0.04)",
    // Neutral
    nearBlack: "#101114",
    coolGray: "#686b82",
    silverBlue: "#9497a9",
    white: "#ffffff",
    fafafa: "#fafafa",
    borderGray: "#dedee5",
    rowDivider: "#f0f0f5",
    // Semantic
    green: "#149e61",
    greenDark: "#026b3f",
    greenSubtle: "rgba(20,158,97,0.16)",
    greenBg: "rgba(20,158,97,0.04)",
    red: "#d63b3b",
    redSubtle: "rgba(214,59,59,0.16)",
  },
  spacing: {
    xs: "4px",
    sm: "8px",
    md: "12px",
    lg: "16px",
    xl: "20px",
    xxl: "24px",
    xxxl: "32px",
  },
  radius: {
    sm: "6px",
    md: "8px",
    lg: "10px",
    xl: "12px",
    pill: "9999px",
  },
  shadow: {
    whisper: "rgba(0,0,0,0.03) 0px 4px 24px",
    micro: "rgba(16,24,40,0.04) 0px 1px 4px",
  },
  font: {
    family: "'Helvetica Neue', Helvetica, Arial, sans-serif",
    sizes: {
      micro: "10px",
      caption: "12px",
      body: "14px",
      h3: "18px",
      h2: "24px",
      h1: "32px",
    },
    weights: {
      regular: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
  },
} as const;
