import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import SearchPage from "./pages/SearchPage";
import EditionPage from "./pages/EditionPage";
import WorkPage from "./pages/WorkPage";
import AuthorPage from "./pages/AuthorPage";
import BrowseEditionsPage from "./pages/BrowseEditionsPage";
import BrowseWorksPage from "./pages/BrowseWorksPage";
import BrowseAuthorsPage from "./pages/BrowseAuthorsPage";
import ModerationPage from "./pages/ModerationPage";
import NotFoundPage from "./pages/NotFoundPage";
import { InfoProvider } from "./context/InfoContext";

function App() {
    return (
        <InfoProvider>
            <Routes>
                <Route element={<Layout />}>
                    <Route index element={<SearchPage />} />
                    <Route path="edition/:identifier" element={<EditionPage />} />
                    <Route path="work/:olId" element={<WorkPage />} />
                    <Route path="author/:olId" element={<AuthorPage />} />
                    <Route path="browse/editions" element={<BrowseEditionsPage />} />
                    <Route path="browse/works" element={<BrowseWorksPage />} />
                    <Route path="browse/authors" element={<BrowseAuthorsPage />} />
                    <Route path="moderate" element={<ModerationPage />} />
                    <Route path="*" element={<NotFoundPage />} />
                </Route>
            </Routes>
        </InfoProvider>
    );
}

export default App;
