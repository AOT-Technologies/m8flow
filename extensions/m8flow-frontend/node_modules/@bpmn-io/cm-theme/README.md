# Codemirror themes

> **Warning**  
> These styles are new and still a work in progress. Expect quite a few changes.

Codemirror themes centralized in an effort to create consistency across the bpmn-io suite.

## Light theme
![image](https://user-images.githubusercontent.com/17801113/228022199-49569983-6d47-4ca5-89eb-63782950734b.png)

## Dark theme
![image](https://user-images.githubusercontent.com/17801113/228022240-c44638c7-3058-436a-87ff-567aa382fffb.png)

## Usage

### Install 
`npm i @bpmn-io/cm-theme`

### Use
```js
import { darkTheme, lightTheme } from '@bpmn-io/cm-theme';
import { EditorView } from '@codemirror/view';


// ...

const extensions = [
    lightTheme
];

// ...

new EditorView({
    state: EditorState.create({
      doc: value,
      extensions: extensions
    }),
    parent: container
});
```
