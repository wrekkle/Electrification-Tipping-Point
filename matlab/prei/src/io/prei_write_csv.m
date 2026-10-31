function prei_write_csv(path, header, rows)
%PREI_WRITE_CSV Write a CSV with a header and a cell matrix of rows.
%   Numbers use %.17g, logicals use 0/1, NaN becomes an empty field, and
%   character fields are quoted only when needed.

if ~iscell(header) || isempty(header)
    error('prei:io:header', 'CSV header must be a nonempty cell array.');
end
if ~iscell(rows) || size(rows, 2) ~= numel(header)
    error('prei:io:rows', 'CSV rows must be a cell matrix with one column per header.');
end

fid = fopen(path, 'w', 'n', 'UTF-8');
if fid < 0
    error('prei:io:open', 'Cannot open output file: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

header_fields = cell(1, numel(header));
for j = 1:numel(header)
    header_fields{j} = prei_csv_field(header{j});
end
fprintf(fid, '%s\n', strjoin(header_fields, ','));

for i = 1:size(rows, 1)
    fields = cell(1, numel(header));
    for j = 1:numel(header)
        value = rows{i, j};
        if ischar(value)
            fields{j} = prei_csv_field(value);
        elseif islogical(value) && isscalar(value)
            fields{j} = sprintf('%d', value);
        elseif isnumeric(value) && isscalar(value)
            if isnan(value)
                fields{j} = '';
            else
                fields{j} = sprintf('%.17g', value);
            end
        else
            error('prei:io:value', 'Unsupported CSV value at row %d column %d.', i, j);
        end
    end
    fprintf(fid, '%s\n', strjoin(fields, ','));
end
end

function field = prei_csv_field(value)
if ~ischar(value)
    error('prei:io:field', 'CSV fields must be character values before formatting.');
end
needs_quote = any(value == ',') || any(value == '"') || ...
    any(value == sprintf('\n')) || any(value == sprintf('\r'));
if needs_quote
    field = ['"' strrep(value, '"', '""') '"'];
else
    field = value;
end
end
