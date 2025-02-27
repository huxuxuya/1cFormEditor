////////////////////////////////////////////////////////////////////////////////
// Модуль "РедакторФорм" содержит процедуры и функции для 
// подготовки форм для работы с нетиповым функционалом системы.
// Документация https://github.com/huxuxuya/1cFormEditor
////////////////////////////////////////////////////////////////////////////////

#Область ПрограммныйИнтерфейс

// Проверяет выполнялась ли уже подготовка формы для работы с нетиповым функционалом системы.
//
// Параметры:
// Форма - УправляемаяФорма
//
Функция ФормаПодготовлена(Форма) Экспорт
	
	Если Форма.Элементы.Найти("ккФормаПодготовлена") = Неопределено Тогда
		ФормаПодготовлена = Форма.Элементы.Добавить("ккФормаПодготовлена", Тип("ДекорацияФормы"));
		ФормаПодготовлена.Видимость = Ложь;
		ФормаПодготовлена.Доступность = Ложь;
	Иначе
		Возврат Истина;
	КонецЕсли;
	
	Возврат Ложь;
	
КонецФункции

// Создает контекст элемента, в рамках которого будет создан элемент
// 
// Параметры:
// 	Форма - УправляемаяФорма - форма для которой выполняется действие.
// 	Родитель - Произвольный - Ссылка на родителя.
// 	РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу.
// 	СвойстваЭлемента - Структура - Структура по которой заполняются свойства.
// Возвращаемое значение:
// 	Структура - Описание:
// 	* Форма - УправляемаяФорма - форма для которой выполняется действие.
//  * Родитель - Произвольный - Ссылка на родителя.
//  * РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. -
//  * Свойства - Структура - Структура по которой заполняются свойства.
Функция НовыйКонтекстЭлемента(Форма, 
								Родитель = Неопределено, 
								РасположитьПередЭлементом = Неопределено, 
								СвойстваЭлемента = Неопределено) Экспорт
	
	СтруктураКонтекст = Новый Структура();
	СтруктураКонтекст.Вставить("Форма", Форма);
	СтруктураКонтекст.Вставить("Родитель", Родитель);
	СтруктураКонтекст.Вставить("РасположитьПередЭлементом", РасположитьПередЭлементом);
	Если СвойстваЭлемента = Неопределено Тогда
		СтруктураКонтекст.Вставить("Свойства", Новый Структура());		
	Иначе
		СтруктураКонтекст.Вставить("Свойства", СвойстваЭлемента);
	КонецЕсли;
	
	Возврат СтруктураКонтекст;
	
КонецФункции

#Область ДобавлениеПолей

// Внимание! Скорее всего вам нужна одна из Функций:
//  - "ДобавитьРеквизитОбъектаНаФорму" 
//  - "ДобавитьПолеНаФормуРеквизитФормы"
// Данная функция используется достаточно редко, для возможности сложной настройки форм.
//
// Функция добавляет поле на форму, необходимо указание свойства ПутьКДанным 
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяПоля - Строка - Имя создааваемого поля.
//
// Возвращаемое значение:
//	ЭлементФормы - добавленный на форму, новый элемент формы.
//	
Функция НовоеПолеФормы(КонтекстЭлемента, ИмяПоля) Экспорт

	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
	
	ПолеФормы = Форма.Элементы.Добавить(ИмяПоля, Тип("ПолеФормы"), Родитель);

	ПолеФормы.Вид = ВидПоляФормы.ПолеВвода;

	ЗаполнитьЗначенияСвойств(ПолеФормы, Свойства);	
	РасположитьПередЭлементом(КонтекстЭлемента, ПолеФормы);
	
	Возврат ПолеФормы;
	
КонецФункции

// Функция добавляет поле на форму для реквизита формы
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.	
//	ИмяРеквизита - Строка - Имя реквизита формы.
//
// Возвращаемое значение:
//	ЭлементФормы - добавленный на форму, новый элемент формы.
//	
Функция НовоеПолеРеквизитаФормы(КонтекстЭлемента, ИмяРеквизита) Экспорт
	
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
		
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		Если Не Свойства.Свойство("ПутьКДанным") Тогда
			Свойства.Вставить("ПутьКДанным", ИмяРеквизита);
		КонецЕсли;
	Иначе
		Свойства = Новый Структура;
		Свойства.Вставить("ПутьКДанным", ИмяРеквизита);
	КонецЕсли;
	
	ПолеФормы = Форма.Элементы.Добавить(ИмяРеквизита, Тип("ПолеФормы"), Родитель);

	ПолеФормы.Вид = ВидПоляФормы.ПолеВвода;

	ЗаполнитьЗначенияСвойств(ПолеФормы, Свойства);
	РасположитьПередЭлементом(КонтекстЭлемента, ПолеФормы);
		
	Свойства.Удалить("ПутьКДанным");
	
	Возврат ПолеФормы;
	
КонецФункции

#КонецОбласти

#Область ДобавлениеГрупп

// Процедура добавляет группу на форму
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяГруппы - Строка - Имя создаваемой группы.
//
// Возвращаемое значение:
//	ЭлементФормы - добавленный на форму, новый элемент формы.
//
Функция НоваяГруппаФормы(КонтекстЭлемента, ИмяГруппы, Заголовок = "") Экспорт
	
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
		
	ГруппаФормы = Форма.Элементы.Добавить(ИмяГруппы, Тип("ГруппаФормы"), Родитель);
	
	Если ЗначениеЗаполнено(Заголовок) Тогда
		ГруппаФормы.Заголовок = Заголовок;
	КонецЕсли;
	
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		ЗаполнитьЗначенияСвойств(ГруппаФормы, Свойства);
	КонецЕсли;
	
	РасположитьПередЭлементом(КонтекстЭлемента, ГруппаФормы);

	Возврат ГруппаФормы;
	
КонецФункции

// Процедура добавляет группу и 2 вложенные группы(ИмяОсновнойГруппы+"Лево" и ИмяОсновнойГруппы+"Право") на форму 
//	основная группа с горизонтальной группировкой, вложенные группы с вертикальной группировкой
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяГруппы - Строка - Имя создаваемой группы.
//
// Возвращаемое значение:
//	ЭлементФормы - добавленный на форму, основная группа, которые содержит группы, которые являются колонками.
//
Функция НоваяГруппаКолонкиЛевоПраво(КонтекстЭлемента, ИмяОсновнойГруппы) Экспорт
	
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
		
	ИмяГруппыЛево = ИмяОсновнойГруппы + "Лево";
	ИмяГруппыПраво = ИмяОсновнойГруппы + "Право";
	
	ГруппаФормы = Форма.Элементы.Добавить(ИмяОсновнойГруппы, Тип("ГруппаФормы"), Родитель);
	
	Если Не ТипЗнч(Свойства) = Тип("Структура") Тогда
		Свойства = Новый Структура;
	КонецЕсли;
	
	#Область ЗначенияПоУмолчанию
	Если Не Свойства.Свойство("Вид") Тогда
		Свойства.Вставить("Вид", ВидГруппыФормы.ОбычнаяГруппа);
	КонецЕсли;
	Если Не Свойства.Свойство("Группировка") Тогда
		Свойства.Вставить("Группировка", ГруппировкаПодчиненныхЭлементовФормы.ГоризонтальнаяВсегда);
	КонецЕсли;
	Если Не Свойства.Свойство("ОтображатьЗаголовок") Тогда
		Свойства.Вставить("ОтображатьЗаголовок", Ложь);
	КонецЕсли;
	#КонецОбласти
	
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		ЗаполнитьЗначенияСвойств(ГруппаФормы, Свойства);
	КонецЕсли;

	РасположитьПередЭлементом(КонтекстЭлемента, ГруппаФормы);
		
	СвойстваВложенных = Новый Структура;
	СвойстваВложенных.Вставить("Вид", Свойства.Вид);
	СвойстваВложенных.Вставить("Группировка", ГруппировкаПодчиненныхЭлементовФормы.Вертикальная);
	СвойстваВложенных.Вставить("ОтображатьЗаголовок", Свойства.ОтображатьЗаголовок);
	
	КонтекстНовогоЭлемента = НовыйКонтекстЭлемента(Форма, ГруппаФормы, , СвойстваВложенных);
	
	НоваяГруппаФормы(КонтекстНовогоЭлемента, ИмяГруппыЛево);
	НоваяГруппаФормы(КонтекстНовогоЭлемента, ИмяГруппыПраво);

	Возврат ГруппаФормы;

КонецФункции

// Добавляет группу на форму, без заголовка, с вертикальной группировкой
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяГруппы - Строка - Имя создаваемой группы.
//
// Возвращаемое значение:
//	ЭлементФормы - добавленный на форму, основная группа, которые содержит группы, которые являются колонками.
//
Функция НоваяГруппаОбычная(КонтекстЭлемента, ИмяЭлемента, Заголовок = "") Экспорт

	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
		
	НовыйЭлемент = Форма.Элементы.Добавить(ИмяЭлемента, Тип("ГруппаФормы"), Родитель);	
	НовыйЭлемент.Вид = ВидГруппыФормы.ОбычнаяГруппа;
	НовыйЭлемент.Отображение = ОтображениеОбычнойГруппы.Нет;
	НовыйЭлемент.Группировка = ГруппировкаПодчиненныхЭлементовФормы.Вертикальная;
	
	Если ЗначениеЗаполнено(Заголовок) Тогда
		НовыйЭлемент.Заголовок = Заголовок;
		НовыйЭлемент.ОтображатьЗаголовок = Истина;
	Иначе 
		НовыйЭлемент.ОтображатьЗаголовок = Ложь;
	КонецЕсли;
		
	РасположитьПередЭлементом(КонтекстЭлемента, НовыйЭлемент);
	
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		ЗаполнитьЗначенияСвойств(НовыйЭлемент, Свойства);
	КонецЕсли;

	Возврат НовыйЭлемент;
	
КонецФункции

// Функция группу кнопок на форму.
//
// Параметры:
//	Форма - УправляемаяФорма - форма для которой выполняется действие.
//	Родитель - КоманднаяПанель - Родитель элемента.
//	РасположитьПередЭлементом - ГруппаФормы; ТаблицаФормы; УправляемаяФорма - Элемент перед которым требуется разместить новый элемент.
//
// Возвращаемое значение:
//	ЭлементФормы - добавленная на форму, группа кнопок формы.
//
Функция НоваяГруппаКнопок(КонтекстЭлемента) Экспорт 
		
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	
	Сч = 0;
	ЭлементНайден = Истина;
	Пока ЭлементНайден = Истина Цикл
		
		Шаблон = НСтр("ru = 'ГруппаКнопокФормы%1'");
		ИмяРеквизита = СтрШаблон(Шаблон, Сч);
		
		Если Форма.Элементы.Найти(ИмяРеквизита) = Неопределено Тогда
			
			ЭлементНайден = Ложь;
			ГруппаКонпокФормы = Форма.Элементы.Добавить(ИмяРеквизита, Тип("ГруппаФормы"), Родитель);
			ГруппаКонпокФормы.Вид = ВидГруппыФормы.ГруппаКнопок;
			
			РасположитьПередЭлементом(КонтекстЭлемента, ГруппаКонпокФормы);
					
			Возврат ГруппаКонпокФормы;
		КонецЕсли;
		Сч = Сч + 1;
	КонецЦикла;
	
КонецФункции

#КонецОбласти

#Область ДобавлениеТаблиц

// Функция добавляет таблицу на форму
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяПоля - Строка - Имя создааваемой таблицы.
//	ПутьКДанным - Строка - Имя создааваемого поля.
//	СтруктураКолонок - Структура - структура, по данным которой будут созданы колонки 
//		у которых значение элемента структуры будет соответствовать реквизиту таблицы, 
//		а ключ будет именем добавляемого поля.
//
Функция НоваяТаблицаФормы(КонтекстЭлемента, ИмяПоля, ПутьКДанным, СтруктураКолонок = Неопределено) Экспорт
	
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
		
	ПолеФормы = Форма.Элементы.Добавить(ИмяПоля, Тип("ТаблицаФормы"), Родитель);
	
	Если Свойства <> Неопределено Тогда
		ЗаполнитьЗначенияСвойств(ПолеФормы, Свойства);
	КонецЕсли;
	
	ПолеФормы.ПутьКДанным = ПутьКДанным;
	
	РасположитьПередЭлементом(КонтекстЭлемента, ПолеФормы);
	
	Если СтруктураКолонок <> Неопределено Тогда
		Для Каждого Элемент Из СтруктураКолонок Цикл
			
			Параметры = Новый Структура;
			Параметры.Вставить("ПутьКДанным", ПутьКДанным + "." + Элемент.Значение);
			КонтекстНовогоЭлемента = НовыйКонтекстЭлемента(Форма, ПолеФормы, , Параметры);
			
			НовоеПолеФормы(КонтекстНовогоЭлемента, Элемент.Ключ);
			
		КонецЦикла;
	КонецЕсли;
	
	Возврат ПолеФормы;
	
КонецФункции

// Функция добавляет поле таблицы на форму
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ПутьТабличнойЧасти - Строка - Путь к табличной части, колонку которая выводится.
//	ИмяКолонкиТабличнойЧасти - Строка - Имя колонки, которая выводится.
//
// Возвращаемое значение:
//	ЭлементФормы - добавленный на форму, новый элемент формы.
//
Функция НовоеПолеТабличнойЧастиформы(КонтекстЭлемента, ПутьТабличнойЧасти, ИмяКолонкиТабличнойЧасти) Экспорт

	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
		
	ПутьКДанным = СокрЛП(ПутьТабличнойЧасти) + "." + СокрЛП(ИмяКолонкиТабличнойЧасти);
	
	МассивПутьКТабличнойЧасти = РазложитьСтрокуВМассивПодстрок(ПутьТабличнойЧасти, ".", Истина);
	ПоследнееСлово = МассивПутьКТабличнойЧасти[МассивПутьКТабличнойЧасти.Количество() - 1];
	ИмяПоляТабличнойЧасти = СокрЛП(ПоследнееСлово) + СокрЛП(ИмяКолонкиТабличнойЧасти);
	
	СвойстваЭлемента = Новый Структура;
	СвойстваЭлемента.Вставить("ПутьКДанным", ПутьКДанным);
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		Для Каждого Эл Из Свойства Цикл
			СвойстваЭлемента.Вставить(Эл.Ключ, Эл.Значение);	
		КонецЦикла;
	КонецЕсли;	
		
	КонтекстНовогоЭлемента = НовыйКонтекстЭлемента(Форма, Родитель, , СвойстваЭлемента);
	ПолеФормы = НовоеПолеФормы(КонтекстНовогоЭлемента, ИмяПоляТабличнойЧасти);
	
	РасположитьПередЭлементом(КонтекстЭлемента, ПолеФормы);

	Возврат ПолеФормы;
	
КонецФункции

#КонецОбласти

#Область ДобавлениеКоманд

// Функция добавляет команду на форму
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяКнопки - Строка - Имя создааваемой кнопки.
//	ВидКнопки - ВидКнопкиФормы - Вид кнопки.
//	ИмяКоманды - Строка - Имя команды.
//
Функция НоваяКнопкаФормы(КонтекстЭлемента, ИмяКнопки, ВидКнопки, ИмяКоманды) Экспорт

	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
			 
	Кнопка = Форма.Элементы.Добавить(ИмяКнопки, Тип("КнопкаФормы"), Родитель);
	Кнопка.Вид = ВидКнопки;
	Кнопка.ИмяКоманды = ИмяКоманды;

	РасположитьПередЭлементом(КонтекстЭлемента, Кнопка);

	Если Свойства <> Неопределено Тогда
		ЗаполнитьЗначенияСвойств(Кнопка, Свойства);
	КонецЕсли;
	
	Возврат Кнопка;
	
КонецФункции

// Функция добавляет команду и гиперссылку на форму
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяКоманды - Строка - Имя создааваемой команды.
//	ПроцедураОбработки - Строка - Имя процедуры обработки.
//	ЗаголовокГиперссылки - Строка - Заголовок команды.
//
Функция НоваяКомандаИГиперссылкаФормы(КонтекстЭлемента, ИмяКоманды, ПроцедураОбработки, ЗаголовокГиперссылки) Экспорт
	
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	РасположитьПередЭлементом = КонтекстЭлемента.РасположитьПередЭлементом;
			
	НоваяКомандаФормы(КонтекстЭлемента,
						ИмяКоманды,
						ПроцедураОбработки,
						ЗаголовокГиперссылки);
	
	СвойстваЭлемента = Новый Структура("Вид", ВидКнопкиФормы.Гиперссылка);
	КонтекстКнопки = НовыйКонтекстЭлемента(Форма, Родитель, РасположитьПередЭлементом, СвойстваЭлемента);
	Кнопка = НоваяКнопкаФормы(КонтекстКнопки,
						ИмяКоманды,
						ВидКнопкиФормы.КнопкаКоманднойПанели,
						ИмяКоманды);
						
	Возврат Кнопка;
	
КонецФункции

// Функция добавляет команду и кнопку командной панели
//  на форму будет добавлена команда с действием "Подключаемый_"+ИмяКоманды
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяКоманды - Строка - Имя создааваемой команды.
//	ЗаголовокКнопки - Строка - Заголовок команды.
//
Функция НоваяКомандаИКнопкаКоманднойПанели(КонтекстЭлемента, ИмяКоманды, ЗаголовокКнопки) Экспорт
	
	ИмяДействия = "Подключаемый_" + ИмяКоманды;
	
	НоваяКомандаФормы(КонтекстЭлемента,
						ИмяКоманды, 
						ИмяДействия,
						ЗаголовокКнопки);
	
	Кнопка = НоваяКнопкаФормы(КонтекстЭлемента,
						ИмяКоманды,
						ВидКнопкиФормы.КнопкаКоманднойПанели,
						ИмяКоманды);
	
	Возврат Кнопка;
	
КонецФункции

// Функция добавляет команду и кнопку формы
//  на форму будет добавлена команда с действием "Подключаемый_"+ИмяКоманды
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяКоманды - Строка - Имя создааваемой команды.
//	ЗаголовокКнопки - Строка - Заголовок команды.
//
Функция НоваяКомандаИКнопкаФормы(КонтекстЭлемента, ИмяКоманды, ЗаголовокКнопки) Экспорт
	
	ИмяДействия = "Подключаемый_" + ИмяКоманды;
	
	НоваяКомандаФормы(КонтекстЭлемента,
						ИмяКоманды, 
						ИмяДействия,
						ЗаголовокКнопки);
	
	Кнопка = НоваяКнопкаФормы(КонтекстЭлемента,
						ИмяКоманды,
						ВидКнопкиФормы.ОбычнаяКнопка,
						ИмяКоманды);
	
	Возврат Кнопка;
	
КонецФункции

// Функция добавляет команду на форму
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяКоманды - Строка - Имя создааваемой команды.
//	ИмяДействия - Строка - Действие команды.
//	Заголовок - Строка - Заголовок команды.
//	Подсказка - Строка - Подсказка команды.
//
Функция НоваяКомандаФормы(КонтекстЭлемента, ИмяКоманды, ИмяДействия, Заголовок, Подсказка = "") Экспорт

	Форма = КонтекстЭлемента.Форма;
	Свойства = КонтекстЭлемента.Свойства;
	
	Команда = Форма.Команды.Добавить(ИмяКоманды);
	Команда.Действие = ИмяДействия;
	Команда.Заголовок = Заголовок;
	Команда.Подсказка = Подсказка;
	
	Если Свойства <> Неопределено Тогда
		ЗаполнитьЗначенияСвойств(Команда, Свойства);
	КонецЕсли;
	
	Возврат Команда;
	
КонецФункции

#КонецОбласти

#Область ДобавлениеРеквизитовОбъекта

// Функция добавляет реквизит объекта определяя ВидПоляФормы по типу значения
//
// Параметры:
//  Форма - УправляемаяФорма - форма для которой выполняется действие.
//	ИмяРеквизита - Строка - Имя создааваемого поля и он же имя реквизита объекта.
//	Родитель - Произвольный - Ссылка на родителя.
//	ЭтоПолеВвода - Булево - Определяет возможность ввода в добавляемое поле
//	Свойства - Структура - Структура по которой заполняются свойства команды.
//	РасположитьПередЭлементом - ВсеЭлементыФормы - Указывает, перед каким элеменом формы разместить добавляемую группу
//
//Пример:
//	РедакторФорм.ДобавитьРеквизитОбъектаНаФорму(ЭтаФорма, "ккВидДоговора", Элементы.ГруппаШапкаПраво);
//
Функция НовыйРеквизитОбъектаФормы(КонтекстЭлемента, ИмяРеквизита) Экспорт
	
	Форма = КонтекстЭлемента.Форма;	
	Свойства = КонтекстЭлемента.Свойства;
	
	ИмяОбъекта = "Объект";
	ОпределитьРеквизитИИмяОбъектаИзСвойств(Свойства, ИмяОбъекта, ИмяРеквизита);
	
	Если ТипЗнч(Форма[ИмяОбъекта][ИмяРеквизита]) = Тип("Булево") Тогда
											
		Если Свойства  = Неопределено Тогда
			Свойства = Новый Структура("ПоложениеЗаголовка", ПоложениеЗаголовкаЭлементаФормы.Право);
		ИначеЕсли Не Свойства.Свойство("ПоложениеЗаголовка") Тогда
			Свойства.Вставить("ПоложениеЗаголовка", ПоложениеЗаголовкаЭлементаФормы.Право);
		КонецЕсли;
		
		Возврат НовоеПолеФлажокФормыРеквизитОбъекта(КонтекстЭлемента, ИмяРеквизита);
	Иначе
		Возврат НовоеПолеФормыРеквизитОбъекта(КонтекстЭлемента, ИмяРеквизита);
	КонецЕсли;

КонецФункции

// Функция добавляет поле реквизита объекта на форму и возвращает добавленный элемент
//
// Параметры:
//  Форма - УправляемаяФорма - форма для которой выполняется действие.
//	ИмяРеквизита - Строка - Имя создааваемого поля и он же имя реквизита объекта.
//	Родитель - Произвольный - Ссылка на родителя.
//	ЭтоПолеВвода - Булево - Определяет возможность ввода в добавляемое поле
//	Свойства - Структура - Структура по которой заполняются свойства команды.
//	РасположитьПередЭлементом - ВсеЭлементыФормы - Указывает, перед каким элеменом формы разместить добавляемую группу
//
//Пример:
//	РедакторФорм.ДобавитьПолеНаФормуРеквизитОбъекта(ЭтаФорма, "ккВидДоговора", Элементы.ГруппаШапкаПраво, Истина);
//
Функция НовоеПолеФормыРеквизитОбъекта(КонтекстЭлемента, ИмяРеквизита) Экспорт
											
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;												
	Свойства = КонтекстЭлемента.Свойства;
		
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		Если Не Свойства.Свойство("ПутьКДанным") Тогда
			Свойства.Вставить("ПутьКДанным", "Объект." + ИмяРеквизита);
		КонецЕсли;
	Иначе
		Свойства = Новый Структура;
		Свойства.Вставить("ПутьКДанным", "Объект." + ИмяРеквизита);
	КонецЕсли;
	
	ПолеФормы = Форма.Элементы.Добавить(ИмяРеквизита, Тип("ПолеФормы"), Родитель);
	ПолеФормы.Вид = ВидПоляФормы.ПолеВвода;
	
	ЗаполнитьЗначенияСвойств(ПолеФормы, Свойства);	
	ЗаполнитьСписокВыбора(ПолеФормы, Свойства);	
	РасположитьПередЭлементом(КонтекстЭлемента, ПолеФормы);
	
	Свойства.Удалить("ПутьКДанным");
	
	Возврат ПолеФормы;
	
КонецФункции

// Функция добавляет поле реквизита объекта на форму с заданным значением МаксимальнаяШирина = 28
//	для вывода в шапку формы, согласно рекомендации адаптации интерфейсов
//
// Параметры:
//  Форма - УправляемаяФорма - форма для которой выполняется действие.
//	ИмяРеквизита - Строка - Имя создааваемого поля и он же имя реквизита объекта.
//	Родитель - Произвольный - Ссылка на родителя.
//	ЭтоПолеВвода - Булево - Определяет возможность ввода в добавляемое поле
//	Свойства - Структура - Структура по которой заполняются свойства команды.
//
//Пример:
//	РедакторФорм.ДобавитьПолеВШапкуФормыРеквизитОбъекта(ЭтаФорма, "ккВидДоговора", Элементы.ГруппаШапкаПраво, Истина);
//
Функция НовоеПолеШапкиФормыРеквизитОбъекта(КонтекстЭлемента, ИмяРеквизита) Экспорт
	
	Свойства = КонтекстЭлемента.Свойства;
											
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		Если Не Свойства.Свойство("АвтоМаксимальнаяШирина") Тогда
			Свойства.Вставить("АвтоМаксимальнаяШирина", Ложь);
			Свойства.Вставить("МаксимальнаяШирина", 28);
		КонецЕсли;
	Иначе
		Свойства = Новый Структура;
		Свойства.Вставить("МаксимальнаяШирина", 28);
		Свойства.Вставить("АвтоМаксимальнаяШирина", Ложь);
	КонецЕсли;
	
	ПолеФормы = НовоеПолеФормыРеквизитОбъекта(КонтекстЭлемента, ИмяРеквизита);
	
	Возврат ПолеФормы;
	
КонецФункции

// Добавляет многострочное поле реквизита объекта и возвращает элемент формы, добавленный на форму.
//
// Параметры:
//	Форма - УправляемаяФорма - форма для которой выполняется действие.
//	ИмяРеквизита - Строка - Имя создааваемого поля и он же имя реквизита объекта.
//	Родитель - ГруппаФормы; ТаблицаФормы; УправляемаяФорма - Родитель элемента.
//	РасположитьПередЭЛементом - ГруппаФормы; ТаблицаФормы; УправляемаяФорма - Элемент перед которым требуется разместить новый элемент.
//	Свойства - Структура - Структура по которой заполняются свойства команды.
//	Высота - Число - Высота многострочного поля.
//
// Возвращаемое значение:
//	ЭлементФормы - добавленный на форму, новый элемент формы.
//
Функция НовоеМногострочноеПолеРеквизитОбъекта(КонтекстЭлемента, ИмяРеквизита, Высота = 2) Экспорт
	
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
			
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		Если Не Свойства.Свойство("ПутьКДанным") Тогда
			Свойства.Вставить("ПутьКДанным", "Объект."+ИмяРеквизита);
		КонецЕсли;
	Иначе
		Свойства = Новый Структура;
		Свойства.Вставить("ПутьКДанным", "Объект."+ИмяРеквизита);
	КонецЕсли;
	
	ПолеФормы = Форма.Элементы.Добавить(ИмяРеквизита, Тип("ПолеФормы"), Родитель);
	ПолеФормы.Вид = ВидПоляФормы.ПолеВвода;
	
	ЗаполнитьЗначенияСвойств(ПолеФормы, Свойства);
	
	РасположитьПередЭлементом(КонтекстЭлемента, ПолеФормы);
	
	ПолеФормы.ПоложениеЗаголовка = ПоложениеЗаголовкаЭлементаФормы.Верх;
	ПолеФормы.РастягиватьПоВертикали = Ложь;
	ПолеФормы.АвтоМаксимальнаяВысота = Ложь;
	ПолеФормы.АвтоМаксимальнаяШирина = Ложь;
	ПолеФормы.МногострочныйРежим = Истина;
	ПолеФормы.Высота = Высота;

	Возврат ПолеФормы;
	
КонецФункции

// Функция добавляет флажок реквизита объекта на форму и возвращает добавленный элемент
//
// Параметры:
//  Форма - УправляемаяФорма - форма для которой выполняется действие.
//	ИмяРеквизита - Строка - Имя создааваемого поля и он же имя реквизита объекта.
//	Родитель - Произвольный - Ссылка на родителя.
//	Свойства - Структура - Структура по которой заполняются свойства команды.
//	РасположитьПередЭЛементом - ГруппаФормы; ТаблицаФормы; УправляемаяФорма - Элемент перед которым требуется разместить новый элемент.
//
//Пример:
//	РедакторФорм.ДобавитьПолеФлажкаНаФормуРеквизитОбъекта(ЭтаФорма, "ккВидДоговора", Элементы.ГруппаШапкаПраво);
//
Функция НовоеПолеФлажокФормыРеквизитОбъекта(КонтекстЭлемента, ИмяРеквизита) Экспорт
	
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
			
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		Если Не Свойства.Свойство("ПутьКДанным") Тогда
			Свойства.Вставить("ПутьКДанным", "Объект."+ИмяРеквизита);
		КонецЕсли;
	Иначе
		Свойства = Новый Структура;
		Свойства.Вставить("ПутьКДанным", "Объект."+ИмяРеквизита);
	КонецЕсли;
	
	ПолеФормы = Форма.Элементы.Добавить(ИмяРеквизита, Тип("ПолеФормы"), Родитель);
	ПолеФормы.Вид = ВидПоляФормы.ПолеФлажка;
	
	ЗаполнитьЗначенияСвойств(ПолеФормы, Свойства);
	
	РасположитьПередЭлементом(КонтекстЭлемента, ПолеФормы);

	Свойства.Удалить("ПутьКДанным");
	
	Возврат ПолеФормы;
	
КонецФункции


#КонецОбласти

#Область ДобавлениеРеквизитовИЭлементвоНаФорму

// Процедура добавляет декорацию формы.
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяДекорации - Строка - Имя создаваемой декорации.
//	Заголовок - Строка - Заголовок декорации.
//	РастягиватьПоГоризонтали - Булево - Растягивать по горизонтали.
//
// Возвращаемое значение:
//	ЭлементФормы - добавленный на форму, новый элемент формы.
// 	
Функция НоваяДекорацияНадпись(КонтекстЭлемента, ИмяДекорации, Заголовок = "", РастягиватьПоГоризонтали = Неопределено) Экспорт
	
	Форма = КонтекстЭлемента.Форма;
	Родитель = КонтекстЭлемента.Родитель;
	Свойства = КонтекстЭлемента.Свойства;
		
	ДекорацияФормы = Форма.Элементы.Добавить(ИмяДекорации, Тип("ДекорацияФормы"), Родитель);
		
	Если РастягиватьПоГоризонтали <> Неопределено Тогда
		ДекорацияФормы.РастягиватьПоГоризонтали = РастягиватьПоГоризонтали;
	КонецЕсли;
	Если ЗначениеЗаполнено(Заголовок) Тогда
		ДекорацияФормы.Заголовок = Заголовок;
	КонецЕсли;
	
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		ЗаполнитьЗначенияСвойств(ДекорацияФормы, Свойства);
	КонецЕсли;
	
	РасположитьПередЭлементом(КонтекстЭлемента, ДекорацияФормы);

	Возврат ДекорацияФормы;
	
КонецФункции

// Функция добавляет на форму динамический список и возвращает добавленный элемент
//
// Параметры:
//  КонтекстЭлемента - Структура - описание окружения создаваемого элемента и его свойств.
// 		* Форма - УправляемаяФорма - форма для которой выполняется действие.
// 		* Родитель - Произвольный - Ссылка на родителя.
//  	* РасположитьПередЭлементом - ВсеЭлементыФормы, Неопределено - Указывает, перед каким элеменом формы разместить добавляемую группу. 
//  	* Свойства - Структура - Структура по которой заполняются свойства.
//	ИмяСписка - Строка - Имя динамического списка
//	ОсновнаяТаблица - Строка - Таблица для вывода
//
//Пример:
//	РедакторФорм.ДобавитьДинамическийСписокФормы(ЭтаФорма, "СписокНоменклатуры", "Справочник.Номенклатура");
//
Функция НовыйДинамическийСписокФормы(КонтекстЭлемента, ИмяСписка, ОсновнаяТаблица) Экспорт
	
	Форма = КонтекстЭлемента.Форма;
	Свойства = КонтекстЭлемента.Свойства;
	
	Если Не ЕстьСвойствоКоллекции(Форма, ИмяСписка) Тогда
		РеквизитДинамическийСписок = Новый РеквизитФормы(ИмяСписка, Новый ОписаниеТипов("ДинамическийСписок"), , ИмяСписка);
		ДобавляемыеРеквизиты = Новый Массив;
	    ДобавляемыеРеквизиты.Добавить(РеквизитДинамическийСписок);
	    Форма.ИзменитьРеквизиты(ДобавляемыеРеквизиты);
	КонецЕсли;
	
	ДинамическийСписок = Форма[ИмяСписка];
	ДинамическийСписок.ОсновнаяТаблица = ОсновнаяТаблица;
	
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		ЗаполнитьЗначенияСвойств(ДинамическийСписок, Свойства);
	КонецЕсли;
	
	РасположитьПередЭлементом(КонтекстЭлемента, ДинамическийСписок);

	Возврат ДинамическийСписок;                                                     
	
КонецФункции

#КонецОбласти

#КонецОбласти

#Область СлужебныеПроцедурыИФункции

Функция ЕстьСвойствоКоллекции(Коллекция, ИмяСвойства)
	
	Идентификатор = Новый УникальныйИдентификатор;
	
	СтруктураАнализируемая = Новый Структура(ИмяСвойства, Идентификатор);
	
	ЗаполнитьЗначенияСвойств(СтруктураАнализируемая, Коллекция);
	
	Возврат СтруктураАнализируемая[ИмяСвойства] <> Идентификатор;
	
КонецФункции

Процедура ЗаполнитьСписокВыбора(ПолеФормы, Свойства)

	Если Свойства.Свойство("СписокВыбора") Тогда		
		СписокВыбора = Свойства.СписокВыбора;
		Если ТипЗнч(СписокВыбора) = Тип("СписокЗначений") Тогда
			Для Каждого ЭлементСпискаВыбора Из СписокВыбора Цикл
				ПолеФормы.СписокВыбора.Добавить(ЭлементСпискаВыбора.Значение, ЭлементСпискаВыбора.Представление);
			КонецЦикла;
			Если СписокВыбора.Количество() > 0 Тогда
				ПолеФормы.КнопкаВыпадающегоСписка = Истина;
			КонецЕсли;
		КонецЕсли;				
	КонецЕсли;
	
КонецПроцедуры

Процедура ПереместитьЭлемент(ПолеФормы, РасположитьПередЭлементом, Родитель, Форма)

	Если Родитель = Неопределено Тогда
		Родитель = Форма;
	КонецЕсли;
	
	Если РасположитьПередЭлементом <> Неопределено Тогда
		Форма.Элементы.Переместить(ПолеФормы, Родитель, РасположитьПередЭлементом);
	КонецЕсли;

КонецПроцедуры

Функция РазложитьСтрокуВМассивПодстрок(Знач Строка, Знач Разделитель = ",", Знач ПропускатьПустыеСтроки = Неопределено, СокращатьНепечатаемыеСимволы = Ложь) Экспорт
	
	Результат = Новый Массив;
	
	// Для обеспечения обратной совместимости.
	Если ПропускатьПустыеСтроки = Неопределено Тогда
		ПропускатьПустыеСтроки = ?(Разделитель = " ", Истина, Ложь);
		Если ПустаяСтрока(Строка) Тогда 
			Если Разделитель = " " Тогда
				Результат.Добавить("");
			КонецЕсли;
			Возврат Результат;
		КонецЕсли;
	КонецЕсли;
	//
	
	Позиция = СтрНайти(Строка, Разделитель);
	Пока Позиция > 0 Цикл
		Подстрока = Лев(Строка, Позиция - 1);
		Если Не ПропускатьПустыеСтроки Или Не ПустаяСтрока(Подстрока) Тогда
			Если СокращатьНепечатаемыеСимволы Тогда
				Результат.Добавить(СокрЛП(Подстрока));
			Иначе
				Результат.Добавить(Подстрока);
			КонецЕсли;
		КонецЕсли;
		Строка = Сред(Строка, Позиция + СтрДлина(Разделитель));
		Позиция = СтрНайти(Строка, Разделитель);
	КонецЦикла;
	
	Если Не ПропускатьПустыеСтроки Или Не ПустаяСтрока(Строка) Тогда
		Если СокращатьНепечатаемыеСимволы Тогда
			Результат.Добавить(СокрЛП(Строка));
		Иначе
			Результат.Добавить(Строка);
		КонецЕсли;
	КонецЕсли;
	
	Возврат Результат;
	
КонецФункции 

Процедура РасположитьПередЭлементом(КонтекстЭлемента, Элемент)

	Форма = КонтекстЭлемента.Форма;
	Родитель = Неопределено;
	
	РасположитьПередЭлементом = Неопределено;
	КонтекстЭлемента.Свойство("Родитель", Родитель);
	КонтекстЭлемента.Свойство("РасположитьПередЭлементом", РасположитьПередЭлементом);

	Если РасположитьПередЭлементом <> Неопределено Тогда
		ПереместитьЭлемент(Элемент, РасположитьПередЭлементом, Родитель, Форма);
	КонецЕсли;
	
КонецПроцедуры

Процедура ОпределитьРеквизитИИмяОбъектаИзСвойств(Свойства, ИмяОбъекта, ИмяРеквизита)
	
	ИмяОбъекта = "Объект";
	Если ТипЗнч(Свойства) = Тип("Структура") Тогда
		Если Свойства.Свойство("ПутьКДанным") Тогда
			ПутьКДанным = Свойства.ПутьКДанным;
			МассивЧастей = РазложитьСтрокуВМассивПодстрок(ПутьКДанным, ".", Истина);
			Если МассивЧастей.Количество() > 1 Тогда
				ИмяОбъекта = МассивЧастей[0];
				ИмяРеквизита = МассивЧастей[1];
			КонецЕсли;
		КонецЕсли;
	КонецЕсли;

КонецПроцедуры

#КонецОбласти


