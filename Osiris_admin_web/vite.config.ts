import { defineConfig, loadEnv } from "vite";

// Production builds are minified (JS and CSS) by default. Library code goes in its own
// chunks: it changes far less often than the app, so a deploy invalidates only the app chunk
// and browsers or a CDN keep serving React and the rest from cache.
export default defineConfig(({ command, mode }) => {
  // A deploy build without the API URL would ship a console that cannot reach the API, so it fails
  // here instead. RENDER is set by Render's build; the Docker image checks the same thing itself.
  // Local `npm run build` (the gate) still works without it: that bundle shows a configuration
  // error instead of the console (API_CONFIG_ERROR in src/api/client.ts).
  if (command === "build" && process.env.RENDER && !loadEnv(mode, process.cwd()).VITE_API_BASE_URL) {
    throw new Error("VITE_API_BASE_URL is not set: set it on the osiris-admin service and redeploy.");
  }
  return {
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
  };
});
