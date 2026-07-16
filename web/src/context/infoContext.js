import { createContext, useContext } from "react";

export const InfoContext = createContext({ info: null, loading: true, error: null });

export function useInfo() {
    return useContext(InfoContext);
}
