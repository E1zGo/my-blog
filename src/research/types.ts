export const MAX_FILE_BYTES = 200 * 1024 * 1024
export const MAX_PAPERS = 20
export const MAX_PAGES = 300
export const MAX_CHARACTERS = 1_000_000
export interface Passage { page: number; text: string; ordinal: number }
export interface Paper {
  id: string; name: string; size: number; pageCount: number; passages: Passage[]
  emptyPages: number[]; createdAt: string; lastPage: number
}
export interface Note {
  id: string; paperId: string; page: number; quote: string; body: string; createdAt: string
}
export interface Hit extends Passage { score: number }
export interface Expansion { term: string; alternatives: string[] }
