/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./accounts/templates/**/*.html",
    "./requisitions/templates/**/*.html",
    "./inventory/templates/**/*.html",
    "./procurement/templates/**/*.html",
    "./receiving/templates/**/*.html",
  ],
  prefix: "tw-",
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {},
  },
  plugins: [],
};