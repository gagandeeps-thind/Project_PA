import { defineConfig } from "vite";

// Production builds are minified (JS and CSS) by default. Library code goes in its own
// chunks: it changes far less often than the app, so a deploy invalidates only the app chunk
// and browsers or a CDN keep serving React and the rest from cache.
export default defineConfig({
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules[\/](react|react-dom|scheduler)[\/]/, priority: 2 },
            { name: "vendor", test: /node_modules[\/]/, priority: 1 },
          ],
        },
      },
    },
  },
});
