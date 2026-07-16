import { Link } from "react-router-dom";

export default function NotFoundPage() {
    return (
        <div className="text-center py-16">
            <h1 className="text-2xl font-bold">Page not found</h1>
            <Link to="/" className="text-blue-600 hover:underline">Back to search</Link>
        </div>
    );
}
