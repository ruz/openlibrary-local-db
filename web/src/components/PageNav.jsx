import { Button } from "flowbite-react";
import { RiArrowLeftSLine, RiArrowRightSLine } from "react-icons/ri";

export default function PageNav({ offset, limit, hasMore, resultCount, onPageChange }) {
    if (offset === 0 && !hasMore) return null;

    return (
        <div className="flex justify-between items-center mt-4">
            <Button size="sm" color="gray" disabled={offset === 0} onClick={() => onPageChange(Math.max(0, offset - limit))}>
                <RiArrowLeftSLine className="mr-1" /> Previous
            </Button>
            <span className="text-xs text-gray-400">Showing results {offset + 1}&ndash;{offset + resultCount}</span>
            <Button size="sm" color="gray" disabled={!hasMore} onClick={() => onPageChange(offset + limit)}>
                Next <RiArrowRightSLine className="ml-1" />
            </Button>
        </div>
    );
}
