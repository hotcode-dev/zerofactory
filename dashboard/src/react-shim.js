// Shim React and hooks from Hermes Plugin SDK
const SDK = (typeof window !== "undefined" && window.__HERMES_PLUGIN_SDK__) || {};
const React = SDK.React || {};

export default React;
export const {
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef,
  useContext,
  useReducer,
  createElement,
  Fragment,
} = SDK.hooks ? { ...React, ...SDK.hooks } : React;
