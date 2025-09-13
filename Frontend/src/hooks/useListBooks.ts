import { useCallback, useState } from "react"
import { BookInfo } from '../types/book';

const useListBooks = () => {
  const [books, setBooks] = useState<BookInfo[]>([]);

  const listBooks = useCallback(async (bookPath: string) => {
    try {
      const listBooksResult = await window.electron.listBooks(bookPath);

      if (!listBooksResult.success) throw listBooksResult.error;

      const booksLoaded = await Promise.all(listBooksResult.result.map(async book => {
        // Always return books without cover processing since we use colored gradients
        return { ...book, cover: '' };
      }));
      setBooks(booksLoaded);
    } catch (error) {
      console.error(error);
    }
  }, [])

  return { books, listBooks };
}

export default useListBooks;
