import { Fragment } from "react";

export default function ExpandableDetail({ rows, expandedId, onToggle, renderSummary, renderDetail, colSpan = 8 }) {
  return rows.map((row) => (
    <Fragment key={row.id}>
      <tr
        className="cursor-pointer border-t border-[#30363d] hover:bg-[#161b22]/80"
        onClick={() => onToggle(row.id)}
      >
        {renderSummary(row, expandedId === row.id)}
      </tr>
      {expandedId === row.id && (
        <tr className="border-t border-[#30363d] bg-[#0d1117]">
          <td colSpan={colSpan} className="p-4">
            {renderDetail(row)}
          </td>
        </tr>
      )}
    </Fragment>
  ));
}
