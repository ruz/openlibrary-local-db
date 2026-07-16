import { useEffect, useState } from "react";
import { getInfo } from "../api/client";
import { InfoContext } from "./infoContext";

export function InfoProvider({ children }) {
    const [info, setInfo] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        getInfo()
            .then((data) => setInfo(data))
            .catch(() => setError("Could not reach the API"))
            .finally(() => setLoading(false));
    }, []);

    return <InfoContext.Provider value={{ info, loading, error }}>{children}</InfoContext.Provider>;
}
