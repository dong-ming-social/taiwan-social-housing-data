# Repo JSON schema

Every document JSON has five top-level keys. The helper builds `metadata`,
`source`, `sections`, and `pages` automatically; you hand-author the
type-specific parts of `structured_data`.

## Top-level keys
| key | content |
| --- | --- |
| `metadata` | `document_name`, `document_type`, `version`, `language` (`zh-Hant`), `pdf_filename`, `json_filename`, `page_count`, `pdf_sha256`, `pdf_encrypted`, `parser` |
| `source` | `official_pdf_url`, `publisher`, `website_owner`, `attribution`, `rights_note` |
| `sections` | array of `{id, title, page_start, page_end, source_pages, content_pages:[{page, text}]}` |
| `structured_data` | `document_type`, `entities`, `tables`, plus type-specific keys |
| `pages` | per page `{page, text, tables, image_count, has_text, is_blank, image_note}` |

`metadata.parser` is fixed to anydoc / firecrawl-anydoc 0.1.9 (see helper).
`source.publisher` = 臺北市住宅及都市更新中心, `website_owner` = 臺北市政府都市發展局.

## `entities` (always present, may be empty lists)
`dates`, `times`, `amounts_twd`, `percentages`, `phone_numbers` — each an array of
`{value, source_pages:[int]}`. Populate only values actually in the text.

## `document_type` values in use
| type | used for | extra structured_data keys |
| --- | --- | --- |
| `resident_handbook` | 住戶規約手冊 | `key_rules`, `schedules`, `fees`, `contacts` |
| `rental_handbook` | 招租手冊 | (entities, tables) |
| `lease_contract` | 租賃契約書 | `contract_terms` |
| `declaration` | 切結書 (附件2/12) | `declarations` |
| `rent_table` | 租金補貼表 (附件3) | `income_tiers`, `rent_after_subsidy`, `renewal_rent_1_1x` |
| `required_documents` | 應備文件 (附件7) | `required_documents` |
| `reference_table` | 評點制辦理情形 (附件5) | `scoring_records`, `columns`, `note` |
| `form` | 申請書封套/撤案申請書 (附件6/8) | `checklist`/`form_fields`, `recipient`, `application_period` |
| `guidance` | 補正事項 (附件9) | `non_correctable_items`, `correctable_items` |
| `regulation` | 管理扣分規定 (附件10) | `penalty_threshold`, `penalty_rules` |

Reuse an existing type when the document matches; introduce a new one only for a
genuinely new document kind, and add a matching structured key.

## Rules
- Filenames mirror the original PDF, extension changed to `.json`.
- Keep `source_pages` on structured items so data traces back to the PDF page.
- For image-only / no-text-layer content, set `image_note` and do **not** guess
  the image's contents.
- JSON is written UTF-8, `ensure_ascii=False`, 2-space indent.
