// Tailwind build config (standalone CLI, see Dockerfile). Colors based on www.svfislisbach.ch.
module.exports = {
  content: ["./templates/**/*.html"],
  theme: {
    extend: {
      fontFamily: { sans: ["Roboto", "sans-serif"] },
      colors: {
        svf: {
          DEFAULT: "#33708C",
          dark: "#125B76",
          accent: "#1F9AC6",
          light: "#B4E3F3",
          pale: "#E7F5FA",
          text: "#333333",
        },
      },
    },
  },
};
