import { Outlet, Link, useLocation } from "react-router-dom";
import { Navbar, Badge, Dropdown } from "flowbite-react";
import { useInfo } from "../context/infoContext";

function NavLink({ to, children }) {
    const location = useLocation();
    const active = location.pathname === to;
    return (
        <Link
            to={to}
            className={`text-sm font-medium ${active ? "text-blue-700" : "text-gray-600 hover:text-blue-700"}`}
        >
            {children}
        </Link>
    );
}

export default function Layout() {
    const { info } = useInfo();
    const location = useLocation();
    const browseActive = location.pathname.startsWith("/browse");

    return (
        <div className="min-h-screen flex flex-col">
            <Navbar fluid className="border-b border-gray-200">
                <Navbar.Brand as={Link} to="/">
                    <span className="self-center whitespace-nowrap text-lg font-semibold">
                        OpenLibrary Local DB
                    </span>
                </Navbar.Brand>
                <div className="flex md:order-2 gap-4 items-center">
                    <a
                        className="text-sm text-blue-600 hover:underline"
                        href="https://github.com/Mozzo1000/openlibrary-local-db"
                        target="_blank"
                        rel="noreferrer"
                    >
                        GitHub
                    </a>
                    <a
                        className="text-sm text-blue-600 hover:underline"
                        href={`${import.meta.env.VITE_API_URL}api/docs`}
                        target="_blank"
                        rel="noreferrer"
                    >
                        API Docs
                    </a>
                </div>
                <Navbar.Collapse>
                    <NavLink to="/">Search</NavLink>
                    <Dropdown
                        inline
                        arrowIcon={false}
                        trigger="hover"
                        label={
                            <span className={`text-sm font-medium ${browseActive ? "text-blue-700" : "text-gray-600 hover:text-blue-700"}`}>
                                Browse
                            </span>
                        }
                    >
                        <Dropdown.Item as={Link} to="/browse/editions">Editions</Dropdown.Item>
                        <Dropdown.Item as={Link} to="/browse/works">Works</Dropdown.Item>
                        <Dropdown.Item as={Link} to="/browse/authors">Authors</Dropdown.Item>
                    </Dropdown>
                    {info?.overrides_enabled && <NavLink to="/moderate">Moderation</NavLink>}
                </Navbar.Collapse>
            </Navbar>

            <main className="flex-1 container mx-auto w-full md:w-10/12 lg:w-8/12 px-4 py-8">
                <Outlet />
            </main>

            <footer className="border-t border-gray-200 py-4">
                <div className="container mx-auto w-full md:w-10/12 lg:w-8/12 px-4 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                    <span>
                        Search powered by{" "}
                        <a href="https://openlibrary.org" className="underline" target="_blank" rel="noreferrer">
                            OpenLibrary
                        </a>
                    </span>
                    {info && (
                        <>
                            <span>&middot;</span>
                            <span>API v{info.version}</span>
                            {info.oldump_date && (
                                <>
                                    <span>&middot;</span>
                                    <span>Dump date: {info.oldump_date}</span>
                                </>
                            )}
                            {info.suggestions_enabled && (
                                <Badge color="success">Suggestions enabled</Badge>
                            )}
                        </>
                    )}
                </div>
            </footer>
        </div>
    );
}
