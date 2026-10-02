export const SDK = (typeof window !== "undefined" && window.__HERMES_PLUGIN_SDK__) || {
  React: {},
  hooks: {},
  fetchJSON: () => Promise.resolve({}),
  utils: {},
};
export const fetchJSON = SDK.fetchJSON;
export const utils = SDK.utils || {};
